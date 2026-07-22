import os
import pandas as pd
import numpy as np

def generate_all():
    fixture_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "tests", "fixtures"))
    os.makedirs(fixture_dir, exist_ok=True)
    print(f"Generating fixtures in: {fixture_dir}")
    
    np.random.seed(42)
    
    sizes = {
        "tiny": 10,
        "medium": 1000,
        "large": 50000
    }
    
    # ─── HR Domain ───
    depts = ["Sales", "HR", "Engineering", "Marketing", "Support"]
    for sz_name, sz in sizes.items():
        hr_df = pd.DataFrame({
            "Employee ID": [f"EMP-{i:06d}" for i in range(1, sz + 1)],
            "Salary": np.random.randint(40000, 180000, size=sz),
            "Department": np.random.choice(depts, size=sz),
            "Hire Date": pd.date_range(start="2018-01-01", periods=sz, freq="h" if sz > 1000 else "D").strftime("%Y-%m-%d"),
            "Performance Rating": np.random.randint(1, 6, size=sz)
        })
        hr_df.to_csv(os.path.join(fixture_dir, f"hr_{sz_name}.csv"), index=False)
        
    # ─── CRM Domain ───
    for sz_name, sz in sizes.items():
        crm_df = pd.DataFrame({
            "Customer ID": [f"CUST-{i:06d}" for i in range(1, sz + 1)],
            "LTV": np.random.uniform(100.0, 25000.0, size=sz).round(2),
            "Churn Risk": np.random.choice([0, 1], size=sz, p=[0.85, 0.15]),
            "Support Tickets": np.random.randint(0, 21, size=sz),
            "Last Interaction Date": pd.date_range(start="2023-01-01", periods=sz, freq="h" if sz > 1000 else "D").strftime("%Y-%m-%d")
        })
        crm_df.to_csv(os.path.join(fixture_dir, f"crm_{sz_name}.csv"), index=False)
        
    # ─── Finance Domain ───
    assets = ["Equities", "Bonds", "Crypto", "Commodities"]
    for sz_name, sz in sizes.items():
        fin_df = pd.DataFrame({
            "Transaction ID": [f"TXN-{i:06d}" for i in range(1, sz + 1)],
            "Amount": np.random.uniform(10.0, 50000.0, size=sz).round(2),
            "Asset Type": np.random.choice(assets, size=sz),
            "Margin": np.random.uniform(0.05, 0.45, size=sz).round(4),
            "Transaction Date": pd.date_range(start="2022-01-01", periods=sz, freq="h" if sz > 1000 else "D").strftime("%Y-%m-%d %H:%M:%S")
        })
        fin_df.to_csv(os.path.join(fixture_dir, f"finance_{sz_name}.csv"), index=False)
        
    # ─── Inventory Domain ───
    suppliers = ["Supplier A", "Supplier B", "Supplier C", "Supplier D"]
    for sz_name, sz in sizes.items():
        inv_df = pd.DataFrame({
            "Item Code": [f"SKU-{i:06d}" for i in range(1, sz + 1)],
            "Stock Level": np.random.randint(0, 1001, size=sz),
            "Reorder Level": np.random.randint(10, 201, size=sz),
            "Unit Cost": np.random.uniform(1.0, 1500.0, size=sz).round(2),
            "Supplier": np.random.choice(suppliers, size=sz)
        })
        inv_df.to_csv(os.path.join(fixture_dir, f"inventory_{sz_name}.csv"), index=False)
        
    print("Fixtures generated successfully!")

if __name__ == "__main__":
    generate_all()
