#ifndef INA226_H
#define INA226_H

#include "main.h"

// Initialize INA226 for Fast Sampling
void INA226_Init(I2C_HandleTypeDef *hi2c);

// Read Bus Voltage and Current
// bus_voltage_V and current_A can be NULL if you don't need them
void INA226_Read_Bus_Voltage_Current(I2C_HandleTypeDef *hi2c, float *bus_voltage_V, float *current_A);

#endif /* INA226_H */
