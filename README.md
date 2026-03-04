# Campus Emergency Supply Distribution Optimization

This project solves an optimization problem for distributing emergency supplies across campus facilities using **Mixed Integer Linear Programming (MILP)** implemented in Python with the **PuLP** optimization library.

## Objective

Minimize the **total annual cost** of distributing supplies while satisfying:

- Facility demand
- Warehouse capacity constraints
- Budget limitations

## Tools Used

- Python
- PuLP
- Pandas


## How to Run

Install dependencies:
pip install pandas pulp


Run the optimization model:
python src/optimization.py


## Output

The program computes:

- Optimal warehouse selection
- Shipment quantities to each facility
- Cost breakdown for transportation, construction, and operations
