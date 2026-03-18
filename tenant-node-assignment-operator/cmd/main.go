package main

import (
	"context"
	"flag"
	"fmt"
	"os"

	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/types"
	clientgoscheme "k8s.io/client-go/kubernetes/scheme"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/healthz"
	"sigs.k8s.io/controller-runtime/pkg/log/zap"
	metricsserver "sigs.k8s.io/controller-runtime/pkg/metrics/server"

	cpv1alpha1 "github.com/compute-platform/tenant-node-assignment-operator/api/v1alpha1"
	"github.com/compute-platform/tenant-node-assignment-operator/internal/config"
	controller "github.com/compute-platform/tenant-node-assignment-operator/internal/controller"
)

var (
	scheme   = runtime.NewScheme()
	setupLog = ctrl.Log.WithName("setup")
)

func init() {
	_ = clientgoscheme.AddToScheme(scheme)
	_ = cpv1alpha1.AddToScheme(scheme)
}

func main() {
	var (
		metricsAddr          string
		enableLeaderElection bool
		probeAddr            string
		configMapNamespace   string
		configMapName        string
	)

	flag.StringVar(&metricsAddr, "metrics-bind-address", ":8080", "The address the metric endpoint binds to.")
	flag.BoolVar(&enableLeaderElection, "leader-elect", true, "Enable leader election for HA. Only one controller will be active at a time.")
	flag.StringVar(&probeAddr, "health-probe-bind-address", ":8081", "The address the health probe endpoint binds to.")
	flag.StringVar(&configMapNamespace, "config-namespace", "compute-platform-system", "Namespace of the operator configuration ConfigMap.")
	flag.StringVar(&configMapName, "config-name", "tenant-node-assignment-operator-config", "Name of the operator configuration ConfigMap.")

	opts := zap.Options{Development: false}
	opts.BindFlags(flag.CommandLine)
	flag.Parse()

	ctrl.SetLogger(zap.New(zap.UseFlagOptions(&opts)))

	mgr, err := ctrl.NewManager(ctrl.GetConfigOrDie(), ctrl.Options{
		Scheme: scheme,
		Metrics: metricsserver.Options{
			BindAddress: metricsAddr,
		},
		HealthProbeBindAddress: probeAddr,
		LeaderElection:         enableLeaderElection,
		LeaderElectionID:       "tenant-node-assignment-operator.computeplatform.io",
	})
	if err != nil {
		setupLog.Error(err, "unable to start manager")
		os.Exit(1)
	}

	// Load operator configuration from ConfigMap or use defaults
	operatorConfig := loadConfig(mgr, configMapNamespace, configMapName)

	setupLog.Info("Loaded operator configuration",
		"workflow", operatorConfig.Workflow.Name,
		"steps", len(operatorConfig.Workflow.Steps),
		"cleanupSteps", len(operatorConfig.Workflow.CleanupSteps),
		"requeueSeconds", operatorConfig.Reconciliation.RequeueSeconds,
	)

	if err = (&controller.TenantNodeAssignmentReconciler{
		Client: mgr.GetClient(),
		Config: operatorConfig,
	}).SetupWithManager(mgr); err != nil {
		setupLog.Error(err, "unable to create controller", "controller", "TenantNodeAssignment")
		os.Exit(1)
	}

	if err := mgr.AddHealthzCheck("healthz", healthz.Ping); err != nil {
		setupLog.Error(err, "unable to set up health check")
		os.Exit(1)
	}
	if err := mgr.AddReadyzCheck("readyz", healthz.Ping); err != nil {
		setupLog.Error(err, "unable to set up ready check")
		os.Exit(1)
	}

	setupLog.Info("starting manager",
		"leaderElection", enableLeaderElection,
		"metricsAddr", metricsAddr,
	)
	if err := mgr.Start(ctrl.SetupSignalHandler()); err != nil {
		setupLog.Error(err, "problem running manager")
		os.Exit(1)
	}
}

// loadConfig attempts to read the configuration ConfigMap. Falls back to defaults.
func loadConfig(mgr ctrl.Manager, namespace, name string) *config.OperatorConfig {
	// Try to read config from cluster ConfigMap
	ctx := context.Background()
	cm := &corev1.ConfigMap{}

	// Use a simple client to read before manager starts
	reader := mgr.GetAPIReader()
	if reader != nil {
		err := reader.Get(ctx, types.NamespacedName{Namespace: namespace, Name: name}, cm)
		if err == nil {
			if yamlData, ok := cm.Data["config.yaml"]; ok {
				cfg, err := config.LoadFromYAML([]byte(yamlData))
				if err != nil {
					setupLog.Error(err, "failed to parse config, using defaults")
					return config.DefaultConfig()
				}
				setupLog.Info(fmt.Sprintf("Loaded workflow %q from ConfigMap %s/%s", cfg.Workflow.Name, namespace, name))
				return cfg
			}
		} else {
			setupLog.Info("Config ConfigMap not found, using defaults", "namespace", namespace, "name", name)
		}
	}

	return config.DefaultConfig()
}
