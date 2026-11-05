/*
 * This file is part of the Silicon Labs Arduino Core
 *
 * The MIT License (MIT)
 *
 * Copyright 2026 Silicon Laboratories Inc. www.silabs.com
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
 * THE SOFTWARE.
 */

#ifndef PIN_CONFIG_H
#define PIN_CONFIG_H

// $[CMU]
// [CMU]$

// $[LFXO]
// [LFXO]$

// $[PRS.ASYNCH0]
// [PRS.ASYNCH0]$

// $[PRS.ASYNCH1]
// [PRS.ASYNCH1]$

// $[PRS.ASYNCH2]
// [PRS.ASYNCH2]$

// $[PRS.ASYNCH3]
// [PRS.ASYNCH3]$

// $[PRS.ASYNCH4]
// [PRS.ASYNCH4]$

// $[PRS.ASYNCH5]
// [PRS.ASYNCH5]$

// $[PRS.ASYNCH6]
// [PRS.ASYNCH6]$

// $[PRS.ASYNCH7]
// [PRS.ASYNCH7]$

// $[PRS.ASYNCH8]
// [PRS.ASYNCH8]$

// $[PRS.ASYNCH9]
// [PRS.ASYNCH9]$

// $[PRS.ASYNCH10]
// [PRS.ASYNCH10]$

// $[PRS.ASYNCH11]
// [PRS.ASYNCH11]$

// $[PRS.ASYNCH12]
// [PRS.ASYNCH12]$

// $[PRS.ASYNCH13]
// [PRS.ASYNCH13]$

// $[PRS.ASYNCH14]
// [PRS.ASYNCH14]$

// $[PRS.ASYNCH15]
// [PRS.ASYNCH15]$

// $[PRS.SYNCH0]
// [PRS.SYNCH0]$

// $[PRS.SYNCH1]
// [PRS.SYNCH1]$

// $[PRS.SYNCH2]
// [PRS.SYNCH2]$

// $[PRS.SYNCH3]
// [PRS.SYNCH3]$

// $[GPIO]
// GPIO SWV on PA03
#ifndef GPIO_SWV_PORT                           
#define GPIO_SWV_PORT                            SL_GPIO_PORT_A
#endif
#ifndef GPIO_SWV_PIN                            
#define GPIO_SWV_PIN                             3
#endif

// [GPIO]$

// $[TIMER0]
// TIMER0 CC0 on PB02
#ifndef TIMER0_CC0_PORT                         
#define TIMER0_CC0_PORT                          SL_GPIO_PORT_B
#endif
#ifndef TIMER0_CC0_PIN                          
#define TIMER0_CC0_PIN                           2
#endif

// [TIMER0]$

// $[TIMER1]
// [TIMER1]$

// $[TIMER2]
// [TIMER2]$

// $[TIMER3]
// [TIMER3]$

// $[TIMER4]
// [TIMER4]$

// $[USART0]
// USART0 RX on PC05
#ifndef USART0_RX_PORT                          
#define USART0_RX_PORT                           SL_GPIO_PORT_C
#endif
#ifndef USART0_RX_PIN                           
#define USART0_RX_PIN                            5
#endif

// USART0 TX on PC04
#ifndef USART0_TX_PORT                          
#define USART0_TX_PORT                           SL_GPIO_PORT_C
#endif
#ifndef USART0_TX_PIN                           
#define USART0_TX_PIN                            4
#endif

// [USART0]$

// $[I2C1]
// [I2C1]$

// $[EUSART1]
// EUSART1 RX on PA08
#ifndef EUSART1_RX_PORT                         
#define EUSART1_RX_PORT                          SL_GPIO_PORT_A
#endif
#ifndef EUSART1_RX_PIN                          
#define EUSART1_RX_PIN                           8
#endif

// EUSART1 SCLK on PB04
#ifndef EUSART1_SCLK_PORT                       
#define EUSART1_SCLK_PORT                        SL_GPIO_PORT_B
#endif
#ifndef EUSART1_SCLK_PIN                        
#define EUSART1_SCLK_PIN                         4
#endif

// EUSART1 TX on PA09
#ifndef EUSART1_TX_PORT                         
#define EUSART1_TX_PORT                          SL_GPIO_PORT_A
#endif
#ifndef EUSART1_TX_PIN                          
#define EUSART1_TX_PIN                           9
#endif

// [EUSART1]$

// $[KEYSCAN]
// [KEYSCAN]$

// $[LETIMER0]
// [LETIMER0]$

// $[IADC0]
// [IADC0]$

// $[ACMP0]
// [ACMP0]$

// $[ACMP1]
// [ACMP1]$

// $[VDAC0]
// [VDAC0]$

// $[VDAC1]
// [VDAC1]$

// $[PCNT0]
// [PCNT0]$

// $[HFXO0]
// [HFXO0]$

// $[I2C0]
// I2C0 SCL on PA07
#ifndef I2C0_SCL_PORT                           
#define I2C0_SCL_PORT                            SL_GPIO_PORT_A
#endif
#ifndef I2C0_SCL_PIN                            
#define I2C0_SCL_PIN                             7
#endif

// I2C0 SDA on PA06
#ifndef I2C0_SDA_PORT                           
#define I2C0_SDA_PORT                            SL_GPIO_PORT_A
#endif
#ifndef I2C0_SDA_PIN                            
#define I2C0_SDA_PIN                             6
#endif

// [I2C0]$

// $[EUSART0]
// EUSART0 RX on PA05
#ifndef EUSART0_RX_PORT                         
#define EUSART0_RX_PORT                          SL_GPIO_PORT_A
#endif
#ifndef EUSART0_RX_PIN                          
#define EUSART0_RX_PIN                           5
#endif

// EUSART0 SCLK on PA03
#ifndef EUSART0_SCLK_PORT                       
#define EUSART0_SCLK_PORT                        SL_GPIO_PORT_A
#endif
#ifndef EUSART0_SCLK_PIN                        
#define EUSART0_SCLK_PIN                         3
#endif

// EUSART0 TX on PA04
#ifndef EUSART0_TX_PORT                         
#define EUSART0_TX_PORT                          SL_GPIO_PORT_A
#endif
#ifndef EUSART0_TX_PIN                          
#define EUSART0_TX_PIN                           4
#endif

// [EUSART0]$

// $[PTI]
// [PTI]$

// $[MODEM]
// [MODEM]$

// $[CUSTOM_PIN_NAME]
#ifndef _PORT                                   
#define _PORT                                    SL_GPIO_PORT_A
#endif
#ifndef _PIN                                    
#define _PIN                                     0
#endif
































// [CUSTOM_PIN_NAME]$


#endif // PIN_CONFIG_H


