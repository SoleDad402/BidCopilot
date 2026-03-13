"""Import all adapters to trigger @AdapterRegistry.register decorators."""
# Tier 1: Free public API adapters
from bidcopilot.discovery.adapters.remoteok import RemoteOKAdapter
from bidcopilot.discovery.adapters.remotive import RemotiveAdapter
from bidcopilot.discovery.adapters.himalayas import HimalayasAdapter
from bidcopilot.discovery.adapters.jobicy import JobicyAdapter
from bidcopilot.discovery.adapters.arbeitnow import ArbeitnowAdapter
from bidcopilot.discovery.adapters.reed import ReedAdapter
from bidcopilot.discovery.adapters.jobright import JobrightAdapter

# ATS platform adapters
from bidcopilot.discovery.adapters.greenhouse import GreenhouseAdapter
from bidcopilot.discovery.adapters.lever import LeverAdapter
from bidcopilot.discovery.adapters.ashby import AshbyAdapter

# Scraping adapters
from bidcopilot.discovery.adapters.weworkremotely import WeWorkRemotelyAdapter
from bidcopilot.discovery.adapters.hn_hiring import HNHiringAdapter

__all__ = [
    "RemoteOKAdapter",
    "RemotiveAdapter",
    "HimalayasAdapter",
    "JobicyAdapter",
    "ArbeitnowAdapter",
    "ReedAdapter",
    "GreenhouseAdapter",
    "LeverAdapter",
    "AshbyAdapter",
    "WeWorkRemotelyAdapter",
    "HNHiringAdapter",
    "JobrightAdapter",
]
