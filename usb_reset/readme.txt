10-5-23

This reset appears to solve pH USB open problem

Web site
https://askubuntu.com/questions/645/how-do-you-reset-a-usb-device-from-the-command-line

Here is lsusb output at time of failure

Bus 002 Device 001: ID 1d6b:0003 Linux Foundation 3.0 root hub
Bus 001 Device 004: ID 248a:8367 Maxxter Telink Wireless Receiver
Bus 001 Device 003: ID 0403:6015 Future Technology Devices International, Ltd Bridge(I2C/SPI/UART/FIFO)
Bus 001 Device 002: ID 2109:3431 VIA Labs, Inc. Hub
Bus 001 Device 001: ID 1d6b:0002 Linux Foundation 2.0 root hub

I picked VIA Labs line 

Issued following command

sudo ./a.out /dev/bus/usb/001/002
Resetting USB device /dev/bus/usb/001/002

See more readme info in script fix that runs command - fix_usb
