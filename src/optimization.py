import pandas as pd
import pulp
import folium


# -----------------------------
# PARAMETERS
# -----------------------------
days = 365
budget = 1500000

# -----------------------------
# LOAD DATA
# -----------------------------
facilities = pd.read_csv("../data/facilities.csv")
demands = pd.read_csv("../data/demands.csv")
warehouses = pd.read_csv("../data/warehouses.csv")
transport = pd.read_csv("../data/transportation_costs.csv")

# Remove extra spaces from column names
facilities.columns = facilities.columns.str.strip()
demands.columns = demands.columns.str.strip()
warehouses.columns = warehouses.columns.str.strip()
transport.columns = transport.columns.str.strip()

# -----------------------------
# MERGE FACILITY + DEMAND
# -----------------------------
facilities = pd.merge(facilities, demands, on="facility_id")

# Annual demand
facilities["annual_demand"] = facilities["daily_demand"] * days

# -----------------------------
# DETECT CAPACITY COLUMN
# -----------------------------
capacity_column = None

for col in warehouses.columns:
    if "capacity" in col.lower():
        capacity_column = col
        break

if capacity_column is None:
    raise Exception("Capacity column not found in warehouses.csv")

# Annual capacity
warehouses["annual_capacity"] = warehouses[capacity_column] * days

# -----------------------------
# DETECT COST COLUMNS
# -----------------------------
construction_col = None
operation_col = None

for col in warehouses.columns:
    if "construction" in col.lower():
        construction_col = col
    if "operational" in col.lower() or "operation" in col.lower():
        operation_col = col

if construction_col is None or operation_col is None:
    raise Exception("Cost columns not found in warehouses.csv")

# -----------------------------
# CREATE TRANSPORT COST DICTIONARY
# -----------------------------
cost_dict = {}

for _, row in transport.iterrows():
    cost_dict[(row["from_warehouse"], row["to_facility"])] = row["cost_per_unit"]

# -----------------------------
# CREATE OPTIMIZATION MODEL
# -----------------------------
model = pulp.LpProblem("Campus_Emergency_Distribution", pulp.LpMinimize)

# Decision variables
ship = pulp.LpVariable.dicts(
    "Ship",
    [(w, f) for w in warehouses["warehouse_id"]
            for f in facilities["facility_id"]],
    lowBound=0
)

open_w = pulp.LpVariable.dicts(
    "OpenWarehouse",
    warehouses["warehouse_id"],
    cat="Binary"
)

# -----------------------------
# OBJECTIVE FUNCTION
# -----------------------------

# Transportation cost
transport_cost = pulp.lpSum(
    ship[w, f] * cost_dict[(w, f)]
    for w in warehouses["warehouse_id"]
    for f in facilities["facility_id"]
)

# Construction cost (amortized over 10 years)
construction_cost = pulp.lpSum(
    open_w[w] *
    warehouses.loc[warehouses["warehouse_id"] == w, construction_col].values[0] / 10
    for w in warehouses["warehouse_id"]
)

# Operational cost
operational_cost = pulp.lpSum(
    open_w[w] *
    warehouses.loc[warehouses["warehouse_id"] == w, operation_col].values[0] * days
    for w in warehouses["warehouse_id"]
)

# Total cost
model += transport_cost + construction_cost + operational_cost

# -----------------------------
# CONSTRAINTS
# -----------------------------

# Demand satisfaction
for f in facilities["facility_id"]:
    demand = facilities.loc[
        facilities["facility_id"] == f, "annual_demand"
    ].values[0]

    model += pulp.lpSum(
        ship[w, f] for w in warehouses["warehouse_id"]
    ) == demand

# Warehouse capacity constraint
for w in warehouses["warehouse_id"]:
    capacity = warehouses.loc[
        warehouses["warehouse_id"] == w, "annual_capacity"
    ].values[0]

    model += pulp.lpSum(
        ship[w, f] for f in facilities["facility_id"]
    ) <= capacity * open_w[w]

# Exactly 2 warehouses must be selected
model += pulp.lpSum(open_w[w] for w in warehouses["warehouse_id"]) == 2

# Budget constraint
model += transport_cost + construction_cost + operational_cost <= budget

# -----------------------------
# SOLVE MODEL
# -----------------------------
model.solve()

# -----------------------------
# RESULTS
# -----------------------------
print("\nStatus:", pulp.LpStatus[model.status])

print("\nSelected Warehouses:")
for w in warehouses["warehouse_id"]:
    if open_w[w].value() == 1:
        print(" ", w)

print("\nShipment Plan:")
for w in warehouses["warehouse_id"]:
    for f in facilities["facility_id"]:
        val = ship[w, f].value()
        if val and val > 0:
            print(f"{w} -> {f} : {val:.2f} units")

print("\nCost Breakdown")
print("------------------")
print("Transportation Cost :", pulp.value(transport_cost))
print("Construction Cost   :", pulp.value(construction_cost))
print("Operational Cost    :", pulp.value(operational_cost))
print("Total Cost          :", pulp.value(model.objective))


# -----------------------------
# CREATE MAP
# -----------------------------

center_lat = facilities["latitude"].mean()
center_lon = facilities["longitude"].mean()

campus_map = folium.Map(
    location=[center_lat, center_lon],
    zoom_start=15,
    tiles="CartoDB positron"
)

# -----------------------------
# ADD WAREHOUSES
# -----------------------------

for _, row in warehouses.iterrows():

    w_id = row["warehouse_id"]
    is_open = open_w[w_id].value() == 1

    color = "green" if is_open else "gray"
    status = "OPEN" if is_open else "CLOSED"

    folium.Marker(
        location=[row["latitude"], row["longitude"]],
        popup=folium.Popup(
            f"<b>Warehouse:</b> {row['warehouse_name']}<br>"
            f"<b>Status:</b> {status}",
            max_width=250
        ),
        icon=folium.Icon(color=color, icon="home")
    ).add_to(campus_map)

# -----------------------------
# ADD FACILITIES
# -----------------------------

for _, row in facilities.iterrows():

    folium.CircleMarker(
        location=[row["latitude"], row["longitude"]],
        radius=7,
        popup=folium.Popup(
            f"<b>Facility:</b> {row['facility_name']}<br>"
            f"<b>Daily Demand:</b> {row['daily_demand']}",
            max_width=250
        ),
        color="red",
        fill=True,
        fill_color="red"
    ).add_to(campus_map)

# -----------------------------
# ROUTING FUNCTION (OSRM)
# -----------------------------

import requests
import time

def get_route(start, end):

    url = f"http://router.project-osrm.org/route/v1/driving/{start[1]},{start[0]};{end[1]},{end[0]}?overview=full&geometries=geojson"

    try:
        r = requests.get(url)
        data = r.json()

        coords = data["routes"][0]["geometry"]["coordinates"]

        return [[c[1], c[0]] for c in coords]

    except:
        return None


# -----------------------------
# DRAW REAL ROAD ROUTES
# -----------------------------

for w in warehouses["warehouse_id"]:

    for f in facilities["facility_id"]:

        qty = ship[w, f].value()

        if qty and qty > 0:

            w_coords = warehouses.loc[
                warehouses["warehouse_id"] == w,
                ["latitude", "longitude"]
            ].values[0]

            f_coords = facilities.loc[
                facilities["facility_id"] == f,
                ["latitude", "longitude"]
            ].values[0]

            route = get_route(w_coords, f_coords)

            if route:

                # thickness based on shipment quantity
                weight = max(2, min(8, qty / 5000))

                folium.PolyLine(
                    locations=route,
                    weight=weight,
                    color="blue",
                    opacity=0.7,
                    tooltip=f"Route: {w} → {f} | Annual Qty: {qty:,.0f}"
                ).add_to(campus_map)

                time.sleep(0.3)  # prevent API rate limits


# -----------------------------
# SAVE MAP
# -----------------------------

campus_map.save("campus_distribution_map.html")

print("\nMap saved as: campus_distribution_map.html")
print("Open the file in your browser to view the logistics network.")