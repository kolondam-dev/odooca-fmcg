"""Physical carton equivalent; unknown dimensions are never silently zero."""
from math import isfinite


def measure(product, quantity):
    dims = [product.carton_qty, product.carton_length_cm, product.carton_width_cm, product.carton_height_cm]
    volume = (quantity / dims[0] * dims[1] * dims[2] * dims[3] / 1000000
              if all(isfinite(v) and v > 0 for v in dims) else None)
    weight = (quantity / product.carton_qty * product.carton_weight_kg
              if product.carton_qty > 0 and isfinite(product.carton_weight_kg)
              and product.carton_weight_kg > 0 else None)
    return volume, weight
