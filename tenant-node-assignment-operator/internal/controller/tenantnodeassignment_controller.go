// Package controller implements the TenantNodeAssignment reconciliation logic
// using a generic, YAML-configurable workflow engine.
package controller

import (
	"context"
	"fmt"
	"time"

	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/errors"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/controller/controllerutil"
	"sigs.k8s.io/controller-runtime/pkg/log"

	cpv1alpha1 "github.com/compute-platform/tenant-node-assignment-operator/api/v1alpha1"
	"github.com/compute-platform/tenant-node-assignment-operator/internal/config"
	"github.com/compute-platform/tenant-node-assignment-operator/internal/labels"
	"github.com/compute-platform/tenant-node-assignment-operator/internal/workflow"
)

const (
	// ControllerFinalizer is the finalizer added to TenantNodeAssignment resources.
	ControllerFinalizer = "computeplatform.io/tenant-node-assignment-controller"
)

// TenantNodeAssignmentReconciler reconciles TenantNodeAssignment objects
// using workflows defined entirely in external YAML configuration.
type TenantNodeAssignmentReconciler struct {
	client.Client
	Config *config.OperatorConfig
}

// +kubebuilder:rbac:groups=computeplatform.io,resources=tenantnodeassignments,verbs=get;list;watch;create;update;patch;delete
// +kubebuilder:rbac:groups=computeplatform.io,resources=tenantnodeassignments/status,verbs=get;update;patch
// +kubebuilder:rbac:groups=computeplatform.io,resources=tenantnodeassignments/finalizers,verbs=update
// +kubebuilder:rbac:groups="",resources=nodes,verbs=get;list;watch;patch;update
// +kubebuilder:rbac:groups="",resources=configmaps,verbs=get;list;watch;create;update;patch
// +kubebuilder:rbac:groups="",resources=events,verbs=create;patch

// Reconcile is the main reconciliation entrypoint. It delegates all business
// logic to the workflow engine, executing steps defined in the operator's
// external ConfigMap (workflow.steps and workflow.cleanupSteps).
func (r *TenantNodeAssignmentReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
	logger := log.FromContext(ctx)
	requeueDuration := time.Duration(r.Config.Reconciliation.RequeueSeconds) * time.Second

	// Step 1: Fetch TenantNodeAssignment
	tna := &cpv1alpha1.TenantNodeAssignment{}
	if err := r.Get(ctx, req.NamespacedName, tna); err != nil {
		if errors.IsNotFound(err) {
			logger.Info("TenantNodeAssignment resource not found, ignoring")
			return ctrl.Result{}, nil
		}
		return ctrl.Result{}, fmt.Errorf("failed to fetch TenantNodeAssignment: %w", err)
	}

	// Build execution context for the workflow engine
	executor := workflow.NewExecutor(r.Client)
	ec := &workflow.ExecutionContext{
		Client: r.Client,
		TNA:    tna,
		TmplData: labels.TemplateData{
			TenantName: tna.Spec.TenantRef.Name,
			NodeName:   tna.Spec.NodeRef.Name,
		},
	}

	// Step 2: Handle deletion — run cleanup workflow
	if !tna.DeletionTimestamp.IsZero() {
		return r.runCleanupWorkflow(ctx, executor, ec, tna)
	}

	// Step 3: Ensure finalizer
	if !controllerutil.ContainsFinalizer(tna, ControllerFinalizer) {
		controllerutil.AddFinalizer(tna, ControllerFinalizer)
		if err := r.Update(ctx, tna); err != nil {
			return ctrl.Result{}, fmt.Errorf("failed to add finalizer: %w", err)
		}
		return ctrl.Result{Requeue: true}, nil
	}

	// Step 4: Check activation
	if !tna.Spec.Activation.Enabled {
		logger.Info("Assignment not activated, skipping")
		return r.updateStatus(ctx, tna, cpv1alpha1.PhasePending, "Assignment not activated")
	}

	// Step 5: Execute the workflow steps from configuration
	wf := r.Config.Workflow
	return r.runWorkflowSteps(ctx, executor, ec, tna, wf.Steps, requeueDuration)
}

// runWorkflowSteps executes the reconciliation workflow steps in order.
func (r *TenantNodeAssignmentReconciler) runWorkflowSteps(
	ctx context.Context,
	executor *workflow.Executor,
	ec *workflow.ExecutionContext,
	tna *cpv1alpha1.TenantNodeAssignment,
	steps []workflow.Step,
	requeueDuration time.Duration,
) (ctrl.Result, error) {
	logger := log.FromContext(ctx)

	for i, step := range steps {
		result := executor.ExecuteStep(ctx, step, ec)

		if result.Failed {
			if step.ContinueOnFailure {
				logger.Info("Step failed but continuing", "step", step.Name, "message", result.Message)
				continue
			}
			failPhase := cpv1alpha1.PhaseFailed
			if step.OnFailure != "" {
				failPhase = cpv1alpha1.TenantNodeAssignmentPhase(step.OnFailure)
			}
			return r.updateStatusWithCondition(ctx, tna, failPhase,
				fmt.Sprintf("Step %q failed: %s", step.Name, result.Message),
				step.Name, metav1.ConditionFalse, "StepFailed")
		}

		if result.Waiting {
			waitPhase := cpv1alpha1.PhaseAwaitingNodeAgent
			if step.OnSuccess != "" {
				waitPhase = cpv1alpha1.TenantNodeAssignmentPhase(step.OnSuccess)
			}
			r.updateStatusWithCondition(ctx, tna, waitPhase,
				fmt.Sprintf("Waiting at step %q: %s", step.Name, result.Message),
				step.Name, metav1.ConditionFalse, "Waiting")
			return ctrl.Result{RequeueAfter: requeueDuration}, nil
		}

		// Step completed
		if step.OnSuccess != "" && result.Modified {
			tna.Status.Phase = cpv1alpha1.TenantNodeAssignmentPhase(step.OnSuccess)
		}
		logger.V(1).Info("Step completed", "step", step.Name, "index", i, "message", result.Message)
	}

	// All steps completed — mark Ready
	return r.updateStatusWithCondition(ctx, tna, cpv1alpha1.PhaseReady,
		"All workflow steps completed", "WorkflowComplete", metav1.ConditionTrue, "AllStepsComplete")
}

// runCleanupWorkflow executes the cleanup workflow steps on CR deletion.
func (r *TenantNodeAssignmentReconciler) runCleanupWorkflow(
	ctx context.Context,
	executor *workflow.Executor,
	ec *workflow.ExecutionContext,
	tna *cpv1alpha1.TenantNodeAssignment,
) (ctrl.Result, error) {
	logger := log.FromContext(ctx)

	if !controllerutil.ContainsFinalizer(tna, ControllerFinalizer) {
		return ctrl.Result{}, nil
	}

	// Execute cleanup steps (best-effort, log failures but continue)
	for _, step := range r.Config.Workflow.CleanupSteps {
		result := executor.ExecuteStep(ctx, step, ec)
		if result.Failed {
			logger.Info("Cleanup step failed (continuing)", "step", step.Name, "message", result.Message)
		} else {
			logger.V(1).Info("Cleanup step completed", "step", step.Name, "message", result.Message)
		}
	}

	// Remove finalizer
	controllerutil.RemoveFinalizer(tna, ControllerFinalizer)
	if err := r.Update(ctx, tna); err != nil {
		return ctrl.Result{}, fmt.Errorf("failed to remove finalizer: %w", err)
	}

	logger.Info("Cleanup workflow completed",
		"tenant", tna.Spec.TenantRef.Name,
		"node", tna.Spec.NodeRef.Name)
	return ctrl.Result{}, nil
}

// updateStatus updates the TNA status phase, message, and observedGeneration.
func (r *TenantNodeAssignmentReconciler) updateStatus(
	ctx context.Context,
	tna *cpv1alpha1.TenantNodeAssignment,
	phase cpv1alpha1.TenantNodeAssignmentPhase,
	message string,
) (ctrl.Result, error) {
	tna.Status.Phase = phase
	tna.Status.Message = message
	tna.Status.ObservedGeneration = tna.Generation
	now := metav1.Now()
	tna.Status.LastTransitionTime = &now
	if err := r.Status().Update(ctx, tna); err != nil {
		return ctrl.Result{}, fmt.Errorf("failed to update status: %w", err)
	}
	return ctrl.Result{}, nil
}

// updateStatusWithCondition updates status phase and sets a Kubernetes condition.
func (r *TenantNodeAssignmentReconciler) updateStatusWithCondition(
	ctx context.Context,
	tna *cpv1alpha1.TenantNodeAssignment,
	phase cpv1alpha1.TenantNodeAssignmentPhase,
	message, conditionType string,
	status metav1.ConditionStatus,
	reason string,
) (ctrl.Result, error) {
	tna.Status.Phase = phase
	tna.Status.Message = message
	tna.Status.ObservedGeneration = tna.Generation
	now := metav1.Now()
	tna.Status.LastTransitionTime = &now

	setCondition(tna, conditionType, status, reason, message)

	if err := r.Status().Update(ctx, tna); err != nil {
		return ctrl.Result{}, fmt.Errorf("failed to update status: %w", err)
	}
	return ctrl.Result{}, nil
}

// setCondition adds or updates a condition on the TenantNodeAssignment.
func setCondition(tna *cpv1alpha1.TenantNodeAssignment, conditionType string, status metav1.ConditionStatus, reason, message string) {
	now := metav1.Now()
	newCondition := metav1.Condition{
		Type:               conditionType,
		Status:             status,
		ObservedGeneration: tna.Generation,
		LastTransitionTime: now,
		Reason:             reason,
		Message:            message,
	}

	for i, c := range tna.Status.Conditions {
		if c.Type == conditionType {
			if c.Status != status {
				tna.Status.Conditions[i] = newCondition
			} else {
				tna.Status.Conditions[i].Reason = reason
				tna.Status.Conditions[i].Message = message
				tna.Status.Conditions[i].ObservedGeneration = tna.Generation
			}
			return
		}
	}
	tna.Status.Conditions = append(tna.Status.Conditions, newCondition)
}

// SetupWithManager sets up the controller with the Manager.
func (r *TenantNodeAssignmentReconciler) SetupWithManager(mgr ctrl.Manager) error {
	return ctrl.NewControllerManagedBy(mgr).
		For(&cpv1alpha1.TenantNodeAssignment{}).
		Owns(&corev1.ConfigMap{}).
		Complete(r)
}
