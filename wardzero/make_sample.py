"""Write synthetic sample datasets (one CSV per scenario). Run: python -m wardzero.make_sample"""
import csv, os
from .synth import PatientSim

def main(out="sample_data"):
    os.makedirs(out, exist_ok=True)
    for name, mode, fault in [("stable", "stable", None), ("slow_deterioration", "slow_deterioration", None),
                              ("acute_event", "acute_event", None), ("sensor_fault_probe_off", "stable", "probe_off")]:
        sim = PatientSim(seed=11)
        rows = [sim.step("stable") for _ in range(192)] + [sim.step(mode, fault) for _ in range(120)]
        with open(f"{out}/{name}.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
        print("wrote", f"{out}/{name}.csv", len(rows), "rows")

if __name__ == "__main__":
    main()
