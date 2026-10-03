import csv
import argparse

def generate_hppc_profile(capacity_ah, output_filename="hppc_profile.csv"):
    # Time resolution
    dt = 1.0  # 1 second
    
    # Currents (Discharge is positive, Charge is negative)
    current_1c = capacity_ah
    current_0_75c = 0.75 * capacity_ah
    current_c_3 = capacity_ah / 3.0
    
    # Durations in seconds
    t_pulse_dis = 30
    t_rest_1 = 40
    t_pulse_chg = 10
    t_rest_2 = 5  # Rest between charge pulse and C/3 discharge
    t_rest_1h = 3600
    
    # Calculate C/3 discharge time to reach exact 10% drop per cycle
    # Ah removed in pulses = (Ah from discharge) - (Ah from charge)
    ah_removed_pulses = (t_pulse_dis * current_1c - t_pulse_chg * current_0_75c) / 3600.0
    ah_to_remove_c3 = (0.1 * capacity_ah) - ah_removed_pulses
    t_dis_c3 = (ah_to_remove_c3 / current_c_3) * 3600.0
    
    data = []
    step_num = 1
    total_time = 0.0
    
    def add_step(stage, current, duration):
        nonlocal step_num, total_time
        data.append([step_num, stage, round(current, 3), round(duration, 1)])
        step_num += 1
        total_time += duration

    # Iterate from 100% down to 10%
    for target_soc in range(100, 9, -10):
        # 1. 1C Discharge pulse
        add_step("Discharging 1C", current_1c, t_pulse_dis)
        
        # 2. Rest
        add_step("Resting", 0, t_rest_1)
        
        # 3. 0.75C Charge pulse (Negative current for charge)
        add_step("Charging 0.75C", -current_0_75c, t_pulse_chg)
        
        # 4. Rest
        add_step("Resting", 0, t_rest_2)
        
        # If not the last step (10% SoC), discharge to next SoC level and rest 1h
        if target_soc > 10:
            add_step("Discharging C/3", current_c_3, t_dis_c3)
            add_step("Resting 1h", 0, t_rest_1h)

    with open(output_filename, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["Step", "Stage", "Current (A)", "Duration (s)"])
        writer.writerows(data)
        
    print(f"HPPC Rig Commands generated successfully: {output_filename}")
    print(f"Total estimated test time: {total_time/3600:.2f} hours")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate HPPC profile CSV")
    parser.add_argument("-c", "--capacity", type=float, help="Cell capacity in Ah")
    parser.add_argument("-o", "--output", type=str, default="hppc_profile.csv", help="Output CSV filename")
    
    args = parser.parse_args()
    
    if args.capacity:
        capacity = args.capacity
    else:
        try:
            capacity = float(input("Enter cell capacity (Ah): "))
        except ValueError:
            print("Invalid capacity entered.")
            exit(1)
            
    generate_hppc_profile(capacity, args.output)
