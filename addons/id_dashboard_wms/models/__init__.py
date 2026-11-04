# Part of odooca-fmcg. License LGPL-3.
# Import order matters: SQL views are created in definition order, so a view must be
# imported after the models and views it reads from.
from . import stock_picking
from . import stock_category
from . import expiry
from . import delivery
from . import fleet_cost
from . import wms_dashboard

from . import delivery_cohort

from . import asset_trip, asset_utilization

from . import pod_attempt

from . import warehouse_structure, warehouse_clock

from . import warehouse_depth
