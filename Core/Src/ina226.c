#include "ina226.h"

#define INA226_I2C_ADDR    (0x40 << 1) // Default I2C Address (A1=GND, A0=GND)
#define REG_CONFIG         0x00
#define REG_SHUNTVOLTAGE   0x01
#define REG_BUSVOLTAGE     0x02
#define REG_CURRENT        0x04
#define REG_CALIBRATION    0x05
#define REG_MASK_ENABLE    0x06

// Initialize INA226 for Fast Sampling
void INA226_Init(I2C_HandleTypeDef *hi2c) {
    uint8_t data[2];

    // 1. Write Calibration Register (CAL = 4096 / 0x1000)
    // NOTE: If you change your shunt resistor, you must recalculate CAL:
    // CAL = 0.00512 / (Current_LSB * R_SHUNT)
    // For 2.5 mOhm (0.0025) and Current_LSB of 0.5 mA (0.0005): CAL = 4096 (0x1000)
    data[0] = 0x10;
    data[1] = 0x00;
    HAL_I2C_Mem_Write(hi2c, INA226_I2C_ADDR, REG_CALIBRATION, I2C_MEMADD_SIZE_8BIT, data, 2, 100);

    // 2. Write Config Register: 140us VBUS, 140us VSHCT, 1 AVG, Continuous (0x0007)
    data[0] = 0x00;
    data[1] = 0x07;
    HAL_I2C_Mem_Write(hi2c, INA226_I2C_ADDR, REG_CONFIG, I2C_MEMADD_SIZE_8BIT, data, 2, 100);

    // 3. (Optional) We skip writing to REG_MASK_ENABLE because the ALERT pin is unconnected.
}

// Read the Bus Voltage and Current by polling since ALERT pin is unconnected
void INA226_Read_Bus_Voltage_Current(I2C_HandleTypeDef *hi2c, float *bus_voltage_V, float *current_A) {
    uint8_t buffer[2];
    
    // Read Bus Voltage (Register 0x02) - Fixed LSB = 1.25 mV/bit
    if (HAL_I2C_Mem_Read(hi2c, INA226_I2C_ADDR, REG_BUSVOLTAGE, I2C_MEMADD_SIZE_8BIT, buffer, 2, 10) == HAL_OK) {
        uint16_t raw_bus = (buffer[0] << 8) | buffer[1];
        if (bus_voltage_V != NULL) {
            *bus_voltage_V = raw_bus * 0.00125f; // Bus Voltage in Volts
        }
    }

    // Read Current (Register 0x04) - LSB = 0.5 mA/bit
    // NOTE: If you changed Current_LSB during calibration, update the 0.0005f multiplier below!
    if (HAL_I2C_Mem_Read(hi2c, INA226_I2C_ADDR, REG_CURRENT, I2C_MEMADD_SIZE_8BIT, buffer, 2, 10) == HAL_OK) {
        int16_t raw_current = (int16_t)((buffer[0] << 8) | buffer[1]);
        if (current_A != NULL) {
            *current_A = raw_current * 0.0005f;  // Current in Amperes
        }
    }
}
