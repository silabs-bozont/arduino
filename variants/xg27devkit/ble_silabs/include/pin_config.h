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
// TIMER0 CC0 on PA04
#ifndef TIMER0_CC0_PORT                         
#define TIMER0_CC0_PORT                          SL_GPIO_PORT_A
#endif
#ifndef TIMER0_CC0_PIN                          
#define TIMER0_CC0_PIN                           4
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
// [USART0]$

// $[USART1]
// USART1 CTS on PA08
#ifndef USART1_CTS_PORT                         
#define USART1_CTS_PORT                          SL_GPIO_PORT_A
#endif
#ifndef USART1_CTS_PIN                          
#define USART1_CTS_PIN                           8
#endif

// USART1 RTS on PA07
#ifndef USART1_RTS_PORT                         
#define USART1_RTS_PORT                          SL_GPIO_PORT_A
#endif
#ifndef USART1_RTS_PIN                          
#define USART1_RTS_PIN                           7
#endif

// USART1 RX on PA06
#ifndef USART1_RX_PORT                          
#define USART1_RX_PORT                           SL_GPIO_PORT_A
#endif
#ifndef USART1_RX_PIN                           
#define USART1_RX_PIN                            6
#endif

// USART1 TX on PA05
#ifndef USART1_TX_PORT                          
#define USART1_TX_PORT                           SL_GPIO_PORT_A
#endif
#ifndef USART1_TX_PIN                           
#define USART1_TX_PIN                            5
#endif

// [USART1]$

// $[I2C1]
// I2C1 SCL on PD03
#ifndef I2C1_SCL_PORT                           
#define I2C1_SCL_PORT                            SL_GPIO_PORT_D
#endif
#ifndef I2C1_SCL_PIN                            
#define I2C1_SCL_PIN                             3
#endif

// I2C1 SDA on PD02
#ifndef I2C1_SDA_PORT                           
#define I2C1_SDA_PORT                            SL_GPIO_PORT_D
#endif
#ifndef I2C1_SDA_PIN                            
#define I2C1_SDA_PIN                             2
#endif

// [I2C1]$

// $[PDM]
// [PDM]$

// $[ETAMPDET]
// [ETAMPDET]$

// $[LETIMER0]
// [LETIMER0]$

// $[IADC0]
// [IADC0]$

// $[ACMP0]
// [ACMP0]$

// $[I2C0]
// [I2C0]$

// $[EUSART0]
// EUSART0 CS on PB02
#ifndef EUSART0_CS_PORT                         
#define EUSART0_CS_PORT                          SL_GPIO_PORT_B
#endif
#ifndef EUSART0_CS_PIN                          
#define EUSART0_CS_PIN                           2
#endif

// EUSART0 RX on PC01
#ifndef EUSART0_RX_PORT                         
#define EUSART0_RX_PORT                          SL_GPIO_PORT_C
#endif
#ifndef EUSART0_RX_PIN                          
#define EUSART0_RX_PIN                           1
#endif

// EUSART0 SCLK on PC02
#ifndef EUSART0_SCLK_PORT                       
#define EUSART0_SCLK_PORT                        SL_GPIO_PORT_C
#endif
#ifndef EUSART0_SCLK_PIN                        
#define EUSART0_SCLK_PIN                         2
#endif

// EUSART0 TX on PC00
#ifndef EUSART0_TX_PORT                         
#define EUSART0_TX_PORT                          SL_GPIO_PORT_C
#endif
#ifndef EUSART0_TX_PIN                          
#define EUSART0_TX_PIN                           0
#endif

// [EUSART0]$

// $[PTI]
// PTI DFRAME on PC05
#ifndef PTI_DFRAME_PORT                         
#define PTI_DFRAME_PORT                          SL_GPIO_PORT_C
#endif
#ifndef PTI_DFRAME_PIN                          
#define PTI_DFRAME_PIN                           5
#endif

// PTI DOUT on PC04
#ifndef PTI_DOUT_PORT                           
#define PTI_DOUT_PORT                            SL_GPIO_PORT_C
#endif
#ifndef PTI_DOUT_PIN                            
#define PTI_DOUT_PIN                             4
#endif

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


