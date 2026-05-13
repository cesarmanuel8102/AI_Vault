"""
Use LEAN CLI programmatically to deploy, bypassing the shell issue.
We call the LEAN CLI's Python API directly.
"""
import os, sys, json

# Change to a clean directory
os.makedirs("C:/AI_VAULT/tmp_agent/lean_workspace", exist_ok=True)
os.chdir("C:/AI_VAULT/tmp_agent/lean_workspace")

# Create a minimal lean.json so CLI doesn't complain
if not os.path.exists("lean.json"):
    with open("lean.json", "w") as f:
        json.dump({"data-folder": "data"}, f)
    os.makedirs("data", exist_ok=True)

# Now let's directly use the LEAN API client
from lean.container import container

# Initialize container
api_client = container.api_client

# Login with our creds
from lean.models.api import QCMinimalLiveAlgorithm

# The container should already be logged in from `lean login` earlier
# Let's try calling the live.start() method directly

brokerage_settings = {
    "id": "InteractiveBrokersBrokerage",
    "ib-agent-description": "Individual",
    "ib-trading-mode": "paper",
    "ib-user-name": "cesarmanuel81",
    "ib-account": "DUM891854",
    "ib-password": "Casiopea8102*",
    "ib-weekly-restart-utc-time": "22:00:00",
    "live-mode-brokerage": "QuantConnect.Brokerages.InteractiveBrokers.InteractiveBrokersBrokerage"
}

data_providers = {
    "InteractiveBrokersBrokerage": {
        "id": "InteractiveBrokersBrokerage"
    }
}

print("Calling api_client.live.start()...")
print(f"  Project: 29490680")
print(f"  CompileId: 91e9aa704f8c13a10e39acd5d5f62604-e27715652009231a5f8a4635045934c0")
print(f"  NodeId: LN-64d4787830461ee45574254f643f69b3")
print(f"  Brokerage: {json.dumps(brokerage_settings, indent=2)}")

try:
    result = api_client.live.start(
        project_id=29490680,
        compile_id="91e9aa704f8c13a10e39acd5d5f62604-e27715652009231a5f8a4635045934c0",
        node_id="LN-64d4787830461ee45574254f643f69b3",
        brokerage_settings=brokerage_settings,
        live_data_providers_settings=data_providers,
        automatic_redeploy=True,
        version_id=-1,
        notify_order_events=False,
        notify_insights=False,
        notify_methods=[]
    )
    print(f"\nSUCCESS!")
    print(f"Result: {result}")
    if hasattr(result, 'get_url'):
        print(f"URL: {result.get_url()}")
except Exception as e:
    print(f"\nERROR: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
