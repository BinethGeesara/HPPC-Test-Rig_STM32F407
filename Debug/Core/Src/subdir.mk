################################################################################
# Automatically-generated file. Do not edit!
# Toolchain: GNU Tools for STM32 (14.3.rel1)
################################################################################

# Add inputs and outputs from these tool invocations to the build variables 
C_SRCS += \
../Core/Src/SEGGER_RTT.c \
../Core/Src/SEGGER_RTT_Syscalls_GCC.c \
../Core/Src/SEGGER_RTT_Syscalls_IAR.c \
../Core/Src/SEGGER_RTT_Syscalls_KEIL.c \
../Core/Src/SEGGER_RTT_Syscalls_SES.c \
../Core/Src/SEGGER_RTT_printf.c \
../Core/Src/main.c \
../Core/Src/stm32f4xx_hal_msp.c \
../Core/Src/stm32f4xx_hal_timebase_tim.c \
../Core/Src/stm32f4xx_it.c \
../Core/Src/syscalls.c \
../Core/Src/sysmem.c \
../Core/Src/system_stm32f4xx.c 

OBJS += \
./Core/Src/SEGGER_RTT.o \
./Core/Src/SEGGER_RTT_Syscalls_GCC.o \
./Core/Src/SEGGER_RTT_Syscalls_IAR.o \
./Core/Src/SEGGER_RTT_Syscalls_KEIL.o \
./Core/Src/SEGGER_RTT_Syscalls_SES.o \
./Core/Src/SEGGER_RTT_printf.o \
./Core/Src/main.o \
./Core/Src/stm32f4xx_hal_msp.o \
./Core/Src/stm32f4xx_hal_timebase_tim.o \
./Core/Src/stm32f4xx_it.o \
./Core/Src/syscalls.o \
./Core/Src/sysmem.o \
./Core/Src/system_stm32f4xx.o 

C_DEPS += \
./Core/Src/SEGGER_RTT.d \
./Core/Src/SEGGER_RTT_Syscalls_GCC.d \
./Core/Src/SEGGER_RTT_Syscalls_IAR.d \
./Core/Src/SEGGER_RTT_Syscalls_KEIL.d \
./Core/Src/SEGGER_RTT_Syscalls_SES.d \
./Core/Src/SEGGER_RTT_printf.d \
./Core/Src/main.d \
./Core/Src/stm32f4xx_hal_msp.d \
./Core/Src/stm32f4xx_hal_timebase_tim.d \
./Core/Src/stm32f4xx_it.d \
./Core/Src/syscalls.d \
./Core/Src/sysmem.d \
./Core/Src/system_stm32f4xx.d 


# Each subdirectory must supply rules for building sources it contributes
Core/Src/%.o Core/Src/%.su Core/Src/%.cyclo: ../Core/Src/%.c Core/Src/subdir.mk
	arm-none-eabi-gcc "$<" -mcpu=cortex-m4 -std=gnu11 -g3 -DDEBUG -DUSE_HAL_DRIVER -DSTM32F407xx -c -I../Core/Inc -IC:/Users/user/STM32Cube/Repository/STM32Cube_FW_F4_V1.28.3/Drivers/STM32F4xx_HAL_Driver/Inc -IC:/Users/user/STM32Cube/Repository/STM32Cube_FW_F4_V1.28.3/Drivers/STM32F4xx_HAL_Driver/Inc/Legacy -IC:/Users/user/STM32Cube/Repository/STM32Cube_FW_F4_V1.28.3/Drivers/CMSIS/Device/ST/STM32F4xx/Include -IC:/Users/user/STM32Cube/Repository/STM32Cube_FW_F4_V1.28.3/Drivers/CMSIS/Include -O0 -ffunction-sections -fdata-sections -Wall -fstack-usage -fcyclomatic-complexity -MMD -MP -MF"$(@:%.o=%.d)" -MT"$@" --specs=nano.specs -mfpu=fpv4-sp-d16 -mfloat-abi=hard -mthumb -o "$@"

clean: clean-Core-2f-Src

clean-Core-2f-Src:
	-$(RM) ./Core/Src/SEGGER_RTT.cyclo ./Core/Src/SEGGER_RTT.d ./Core/Src/SEGGER_RTT.o ./Core/Src/SEGGER_RTT.su ./Core/Src/SEGGER_RTT_Syscalls_GCC.cyclo ./Core/Src/SEGGER_RTT_Syscalls_GCC.d ./Core/Src/SEGGER_RTT_Syscalls_GCC.o ./Core/Src/SEGGER_RTT_Syscalls_GCC.su ./Core/Src/SEGGER_RTT_Syscalls_IAR.cyclo ./Core/Src/SEGGER_RTT_Syscalls_IAR.d ./Core/Src/SEGGER_RTT_Syscalls_IAR.o ./Core/Src/SEGGER_RTT_Syscalls_IAR.su ./Core/Src/SEGGER_RTT_Syscalls_KEIL.cyclo ./Core/Src/SEGGER_RTT_Syscalls_KEIL.d ./Core/Src/SEGGER_RTT_Syscalls_KEIL.o ./Core/Src/SEGGER_RTT_Syscalls_KEIL.su ./Core/Src/SEGGER_RTT_Syscalls_SES.cyclo ./Core/Src/SEGGER_RTT_Syscalls_SES.d ./Core/Src/SEGGER_RTT_Syscalls_SES.o ./Core/Src/SEGGER_RTT_Syscalls_SES.su ./Core/Src/SEGGER_RTT_printf.cyclo ./Core/Src/SEGGER_RTT_printf.d ./Core/Src/SEGGER_RTT_printf.o ./Core/Src/SEGGER_RTT_printf.su ./Core/Src/main.cyclo ./Core/Src/main.d ./Core/Src/main.o ./Core/Src/main.su ./Core/Src/stm32f4xx_hal_msp.cyclo ./Core/Src/stm32f4xx_hal_msp.d ./Core/Src/stm32f4xx_hal_msp.o ./Core/Src/stm32f4xx_hal_msp.su ./Core/Src/stm32f4xx_hal_timebase_tim.cyclo ./Core/Src/stm32f4xx_hal_timebase_tim.d ./Core/Src/stm32f4xx_hal_timebase_tim.o ./Core/Src/stm32f4xx_hal_timebase_tim.su ./Core/Src/stm32f4xx_it.cyclo ./Core/Src/stm32f4xx_it.d ./Core/Src/stm32f4xx_it.o ./Core/Src/stm32f4xx_it.su ./Core/Src/syscalls.cyclo ./Core/Src/syscalls.d ./Core/Src/syscalls.o ./Core/Src/syscalls.su ./Core/Src/sysmem.cyclo ./Core/Src/sysmem.d ./Core/Src/sysmem.o ./Core/Src/sysmem.su ./Core/Src/system_stm32f4xx.cyclo ./Core/Src/system_stm32f4xx.d ./Core/Src/system_stm32f4xx.o ./Core/Src/system_stm32f4xx.su

.PHONY: clean-Core-2f-Src

