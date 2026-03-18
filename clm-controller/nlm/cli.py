"""NLM CLI — Click-based command-line tool."""
from __future__ import annotations
import json
import sys
import os
import click
from rich.console import Console
from rich.table import Table

# Ensure nlm package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from nlm import db
from nlm.models import NodeState, CordonPriority, Severity
from nlm.statemachine import StateMachine, TransitionDeniedError
from nlm.classifier import classify, IncidentCorrelator, RULES
from nlm.cordon import cordon as do_cordon, uncordon as do_uncordon, CordonDeniedError
from nlm.alerts import send_alert
from nlm.mock_fleet import seed_fleet, seed_netbox_devices

console = Console()
sm = StateMachine()
correlator = IncidentCorrelator()


@click.group()
def cli():
    """NLM — Node Lifecycle Management CLI"""
    pass


@cli.command()
def setup():
    """Initialize database and seed 50-node mock fleet."""
    db.init_db()
    count = seed_fleet()
    nb_count = seed_netbox_devices()
    console.print(f"✅ Database initialized: nlm-data/nlm.db")
    console.print(f"✅ Seeded {count} mock nodes (GPU + CPU)")
    console.print(f"✅ Seeded {nb_count} NetBox device records")
    console.print(f"\n🚀 Ready! Try: python -m nlm.cli status")


@cli.command()
@click.option("--state", default=None, help="Filter by state")
@click.option("--az", default=None, help="Filter by AZ")
@click.option("--type", "node_type", default=None, help="Filter by type (gpu/cpu)")
@click.option("--node", default=None, help="Show single node details")
def status(state, az, node_type, node):
    """Show fleet status or single node details."""
    if node:
        n = db.get_node(node)
        if not n:
            console.print(f"❌ Node {node} not found"); return
        t = Table(title=f"Node: {n.id}", show_lines=True)
        t.add_column("Field", style="bold cyan"); t.add_column("Value")
        t.add_row("FQDN", n.fqdn)
        t.add_row("Type", n.node_type.value.upper())
        t.add_row("State", f"[bold]{n.state.value}[/bold]")
        t.add_row("State Since", str(n.state_since))
        t.add_row("Environment", n.location.environment)
        t.add_row("AZ", n.location.az)
        t.add_row("Rack", f"{n.location.rack} (pos {n.location.position})")
        t.add_row("PDU", n.location.pdu)
        t.add_row("Switch", f"{n.location.switch}:{n.location.switch_port}")
        t.add_row("SKU", n.hardware.sku)
        t.add_row("GPU", f"{n.hardware.gpu_count}× {n.hardware.gpu_model}" if n.hardware.gpu_count else "N/A")
        t.add_row("CPU", f"{n.hardware.cpu_cores} cores ({n.hardware.cpu_model})")
        t.add_row("RAM", f"{n.hardware.ram_gb} GB")
        t.add_row("Backend", n.backend.value)
        t.add_row("Cordoned", "✅" if n.cordon.is_cordoned else "❌")
        if n.cordon.is_cordoned:
            t.add_row("Cordon Owner", n.cordon.owner)
            t.add_row("Cordon Priority", n.cordon.priority.value)
            t.add_row("Cordon Reason", n.cordon.reason)
        t.add_row("Tenant", n.tenant or "—")
        t.add_row("Protected", "✅" if n.customer_protected else "❌")
        t.add_row("Health Score", f"{n.health_score:.1f}")
        t.add_row("Last Certified", str(n.last_certified) if n.last_certified else "Never")
        t.add_row("Cert Status", n.cert_status or "—")
        t.add_row("Firmware", f"Driver: {n.firmware.gpu_driver}  CUDA: {n.firmware.cuda}")
        console.print(t)
        return

    nodes = db.list_nodes(state=state, az=az, node_type=node_type)
    t = Table(title=f"NLM Fleet Status ({len(nodes)} nodes)")
    t.add_column("Node ID", style="cyan")
    t.add_column("Type")
    t.add_column("State", style="bold")
    t.add_column("Environment")
    t.add_column("Rack")
    t.add_column("SKU")
    t.add_column("Health")
    t.add_column("Tenant")
    t.add_column("Cordoned")
    for n in nodes:
        state_style = "green" if n.state.value in ("certified_ready", "customer_assigned") else \
                      "red" if n.state.value in ("rma", "repair", "emergency_drain") else "yellow"
        t.add_row(
            n.id, n.node_type.value.upper(),
            f"[{state_style}]{n.state.value}[/{state_style}]",
            n.location.environment, n.location.rack, n.hardware.sku,
            f"{n.health_score:.1f}", n.tenant or "—",
            "✅" if n.cordon.is_cordoned else "",
        )
    console.print(t)


@cli.command()
def capacity():
    """Show fleet capacity summary (GPU + CPU by AZ, SKU, state)."""
    cap = db.get_fleet_capacity()
    console.print(f"\n[bold]Total Nodes: {cap['total']}[/bold]\n")

    t = Table(title="By State")
    t.add_column("State"); t.add_column("Count", justify="right")
    for s, c in sorted(cap["by_state"].items()):
        t.add_row(s, str(c))
    console.print(t)

    t2 = Table(title="By AZ")
    t2.add_column("AZ"); t2.add_column("Count", justify="right")
    for a, c in sorted(cap["by_az"].items()):
        t2.add_row(a, str(c))
    console.print(t2)

    t3 = Table(title="By SKU")
    t3.add_column("SKU"); t3.add_column("Count", justify="right")
    for s, c in sorted(cap["by_sku"].items()):
        t3.add_row(s, str(c))
    console.print(t3)

    t4 = Table(title="By Type")
    t4.add_column("Type"); t4.add_column("Count", justify="right")
    for tp, c in sorted(cap["by_type"].items()):
        t4.add_row(tp.upper(), str(c))
    console.print(t4)


@cli.command()
@click.argument("node_id")
@click.option("--trigger", required=True, help="Transition trigger")
@click.option("--operator", default="cli-user", help="Who is doing this")
def transition(node_id, trigger, operator):
    """Trigger a state transition on a node."""
    n = db.get_node(node_id)
    if not n:
        console.print(f"❌ Node {node_id} not found"); return
    try:
        event = sm.transition(n, trigger, operator)
        db.save_node(n)
        db.save_event(event)
        console.print(f"✅ [{event.from_state.value}] → [{event.to_state.value}] (trigger: {trigger})")
    except TransitionDeniedError as e:
        console.print(f"❌ {e}")


@cli.command("cordon")
@click.argument("node_id")
@click.option("--owner", required=True)
@click.option("--priority", default="P3")
@click.option("--reason", default="")
def cordon_cmd(node_id, owner, priority, reason):
    """Cordon a node with priority."""
    n = db.get_node(node_id)
    if not n:
        console.print(f"❌ Node {node_id} not found"); return
    try:
        result = do_cordon(n, owner, CordonPriority(priority), reason)
        db.save_node(n)
        console.print(f"✅ Cordoned: {node_id} by {owner} (P={priority})")
    except CordonDeniedError as e:
        console.print(f"❌ {e}")


@cli.command("uncordon")
@click.argument("node_id")
@click.option("--requester", required=True)
@click.option("--force", is_flag=True, default=False)
def uncordon_cmd(node_id, requester, force):
    """Uncordon a node."""
    n = db.get_node(node_id)
    if not n:
        console.print(f"❌ Node {node_id} not found"); return
    try:
        result = do_uncordon(n, requester, force)
        db.save_node(n)
        console.print(f"✅ Uncordoned: {node_id}")
    except CordonDeniedError as e:
        console.print(f"❌ {e}")


@cli.command()
@click.argument("node_id")
@click.option("--fault", required=True, help="Fault type (e.g. xid_79, psu_fail, ib_crc_high)")
@click.option("--details", default="", help="Additional info")
def inject(node_id, fault, details):
    """Inject a fault into a node for testing."""
    n = db.get_node(node_id)
    if not n:
        console.print(f"❌ Node {node_id} not found"); return

    result = classify(fault, details)
    console.print(f"\n🔍 Classification:")
    console.print(f"  Failure: {result.failure_class.value}")
    console.print(f"  Confidence: {result.confidence:.0%}")
    console.print(f"  Severity: {result.severity.value}")
    console.print(f"  Action: {result.recommended_action}")
    console.print(f"  Route To: {result.route_to}")

    # Auto-cordon if critical/high
    if result.severity in (Severity.CRITICAL, Severity.HIGH):
        try:
            do_cordon(n, "nlm-controller", CordonPriority.P0, result.recommended_action)
            console.print(f"\n⚡ Auto-cordoned: {node_id} (P0)")
        except CordonDeniedError:
            console.print(f"\n⚠  Already cordoned at higher/equal priority")

    correlator.add_event(n, fault)
    incidents = correlator.check_correlations()
    for inc in incidents:
        db.save_incident(inc)
        console.print(f"\n🚨 INCIDENT CREATED: {inc.id} — {inc.details}")

    n.health_score = max(0.0, n.health_score - 0.3)
    send_alert(n, result.severity, result.route_to,
               f"[{fault}] {result.details} → {result.recommended_action}")
    db.save_node(n)


@cli.command()
def rules():
    """Show all classifier rules."""
    t = Table(title=f"Failure Classification Rules ({len(RULES)})")
    t.add_column("#", justify="right"); t.add_column("Event", style="cyan")
    t.add_column("Classification"); t.add_column("Confidence")
    t.add_column("Severity"); t.add_column("Action"); t.add_column("Route To")
    for r in RULES:
        t.add_row(str(r["id"]), r["event"], r["class"].value,
                  f"{r['confidence']:.0%}", r["severity"].value,
                  r["action"], r["route"])
    console.print(t)


@cli.command()
@click.option("--rack", default=None, help="Filter by rack")
def racks(rack):
    """Show rack view (NetBox mock)."""
    nodes = db.list_nodes()
    rack_map: dict[str, list] = {}
    for n in nodes:
        r = n.location.rack
        if rack and r != rack:
            continue
        if r not in rack_map:
            rack_map[r] = []
        rack_map[r].append(n)

    for r_name in sorted(rack_map):
        t = Table(title=f"Rack: {r_name}")
        t.add_column("Pos", justify="right"); t.add_column("Node", style="cyan")
        t.add_column("Type"); t.add_column("SKU"); t.add_column("State")
        t.add_column("Health"); t.add_column("Tenant"); t.add_column("Cordon")
        for n in sorted(rack_map[r_name], key=lambda x: x.location.position):
            t.add_row(str(n.location.position), n.id, n.node_type.value.upper(),
                      n.hardware.sku, n.state.value, f"{n.health_score:.1f}",
                      n.tenant or "—", n.cordon.owner or "—")
        console.print(t)
        console.print("")


@cli.command()
def alerts():
    """Show recent alerts."""
    from nlm.alerts import get_recent_alerts
    recent = get_recent_alerts(30)
    t = Table(title=f"Recent Alerts ({len(recent)})")
    t.add_column("Time"); t.add_column("Sev"); t.add_column("Node")
    t.add_column("Channel"); t.add_column("Message")
    for a in recent:
        t.add_row(a["timestamp"][:19], a["severity"], a["node_id"],
                  a["channel"], a["message"][:60])
    console.print(t)


if __name__ == "__main__":
    cli()
