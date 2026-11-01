#!/bin/zsh
# Lets the Multi Bot extension's «VideoKey Studio» button start the studio (install.py). Run once.
cd "${0:A:h}"
/usr/bin/python3 install.py
echo
echo "Можна закрити це вікно."
