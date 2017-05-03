#!/usr/bin/python
# -*- coding: utf-8 -*-
#
import sys
import time
import os
import errno
import threading

import ConfigParser

import wiringpi

import nfc
from binascii import hexlify

#
#  for GPIO
#
alreadyInit = False

def safeSetupGpio():
  global alreadyInit

  if alreadyInit == False:
    wiringpi.wiringPiSetupGpio()
    alreadyInit = True

#
#  Servo Motor Control
#
class ServoMotor:
  def __init__(self):
    self.readyGpio = alreadyInit
    self.PWM_PIN=[18, 13]
    self.pwm_range = 1920
    self.pwm_clock = 200
    self.pin=0

  def initGpio(self):
    if self.readyGpio == False:
      safeSetupGpio()
      self.readyGpio = True

  def setup(self,id):
    self.initGpio()
    self.pin=id

    if id in self.PWM_PIN:
      self.setupPwm(id)
    else:
     self.setupSoftPwm(id)

  def setupPwm(self, id):
    wiringpi.pinMode(id, wiringpi.GPIO.PWM_OUTPUT)
    wiringpi.pwmSetMode(wiringpi.GPIO.PWM_MODE_MS)
    wiringpi.pwmSetRange(self.pwm_range)
    wiringpi.pwmSetClock(self.pwm_clock)
    self.pin=id

  def setupSoftPwm(self,id):
    wiringpi.pinMode(id, wiringpi.GPIO.PWM_OUTPUT)
    wiringpi.softPwmCreate(id, 0, self.pwm_clock/2)
    self.pin=id

  def pwmWrite(self, angle):
    if self.pin in self.PWM_PIN:
      wiringpi.pwmWrite(self.pin, angle)
    else:
      wiringpi.softPwmWrite(self.pin, angle/10)

  def rotate(self, angle):
    self.pwmWrite(angle)
    if angle > 0:
      time.sleep(0.6)
      self.pwmWrite(0)

  def motor_main(id, angle):
    motor = ServoMotor()
    motor.setup(id)
    motor.rotate(angle)

#
#
#
class Switch(threading.Thread):
  def __init__(self, pin=17):
    threading.Thread.__init__(self)
    self.lock = threading.Lock()
    self.readyGpio = alreadyInit
    self.state = [0,0]
    self.long_state = [0,0,0,0,0]
    self.intval = 0.1
    self.__callback = None
    self.__callback_l = self.stop
    self.initGpio()
    self.setPin(pin)

  def initGpio(self):
    if self.readyGpio == False:
      safeSetupGpio()
      self.readyGpio = True

  def setPin(self, no):
    self.pin = no
    wiringpi.pinMode(self.pin, wiringpi.GPIO.INPUT)

  def sw_state(self):
    state = wiringpi.digitalRead(self.pin)
    self.state.insert(0, state)
    self.state.pop()
    self.long_state.insert(0, state)
    self.long_state.pop()
    return state

  def set_callback(self, func):
    self.__callback=func

  def set_callback_long(self, func):
    self.__callback_l=func

  def start(self, func=None, func_l=None):
    if func : self.__callback=func
    if func_l : self.__callback_l=func_l
    self.mainloop = True
    threading.Thread.start(self)

  def stop(self):
    self.mainloop = False

  def run(self):
    while self.mainloop:
       self.sw_state()
       if self.__callback_l and self.long_state == [1,1,1,1,1]:
         self.__callback_l() 
         self.long_state == [0,0,0,0,0]

       elif self.__callback and self.state == [0,1]:
         self.__callback() 

       time.sleep(self.intval)
    print "Terminate(Switch)"

  def alert(self):
    print "Push"

#
# Led
#
class Led:
  def __init__(self, pin=23):
    self.readyGpio = alreadyInit
    self.state = 0
    self.intval = 0.3
    self.initGpio()
    self.setPin(pin)

  def initGpio(self):
    if self.readyGpio == False:
      safeSetupGpio()
      self.readyGpio = True

  def setPin(self, no):
    self.pin = no
    wiringpi.pinMode(self.pin, wiringpi.GPIO.OUTPUT)

  def led_on(self):
    wiringpi.digitalWrite(self.pin, 1)
    self.state = 1
    return self.state

  def led_off(self):
    wiringpi.digitalWrite(self.pin, 0)
    self.state = 0
    return self.state

  def led_pattern(self, p, tm=0.3):
    self.intval=tm 
    for x in p:
      wiringpi.digitalWrite(self.pin, x)
      time.sleep(self.intval)
    wiringpi.digitalWrite(self.pin, 0)

#
# Buzzer
#
class Buzzer:
  def __init__(self, pin=4):
    self.readyGpio = alreadyInit
    self.state = 0
    self._pipo = [500,1000]
    self._popi = [1000,500]
    self._boo = [500,0,500,500]

    self.initGpio()
    self.setPin(pin)

  def initGpio(self):
    if self.readyGpio == False:
      safeSetupGpio()
      self.readyGpio = True

  def setPin(self, no):
    self.pin = no
    wiringpi.pinMode(self.pin, wiringpi.GPIO.OUTPUT)
    wiringpi.softToneCreate(self.pin)

  def beep(self, tones):
    for hz in tones:
      wiringpi.softToneWrite(self.pin, hz)
      time.sleep(0.1)
    wiringpi.softToneWrite(self.pin, 0)

  def pipo(self):
    self.beep(self._pipo)

  def popi(self):
    self.beep(self._popi)

  def boo(self):
    self.beep(self._boo)


#
#  NFC
#
class ContactlessReader(nfc.ContactlessFrontend):
  def wait_card(self, func, timeout=0):
    if timeout > 0:
      tout = lambda: time.time() - self.started > timeout
      self.started = time.time()
      return self.connect(rdwr={'on-connect': func},terminate=tout)
    else:
      return self.connect(rdwr={'on-connect': func})

class NfcReader:
  def __init__(self):
    self.open_device()
    self.registeredCards = []
    self.clear_id()

  def open_device(self, typ='usb'):
    try:
      self.clf = ContactlessReader(typ)
    except:
      print "Fail to open device"
      self.clf = None
      
  def check_services(self, tag, start, n):
    services = [nfc.tag.tt3.ServiceCode(i >> 6, i & 0x3f)
                for i in xrange(start, start+n)]
    versions = tag.request_service(services)
    for i in xrange(n):
        if versions[i] == 0xffff: continue
        print services[i], versions[i]

  def get_id(self, tag):
    return tag.identifier.encode("hex")
   
  def set_registered_cards(self, cards):
    if type(cards) == str:
      self.registeredCards = cards.split(',')
    elif type(cards) == list:
      self.registeredCards = cards
    else:
      print "Invalid arguments in set_registered_cards"

  def register_card(self, tag):
    id = self.get_id(tag)
    if id in self.registeredCards :
      print "Already registered : %s" % id
    else:
      self.registeredCards.append(id)
      print "Register card : %s" % id

  def check_card(self, tag):
    id = self.get_id(tag)
    if id in self.registeredCards :
      self.callback['check_card']
    else:
      self.registeredCards.append(id)

  def print_tag_info(self, tag):
    print tag.type
    print self.get_id(tag)
   
  def show_tag_info(self, tag):
    print tag
    services = tag.dump()
    for x in services:
      print x

  def show_syscode(self, tag):
    system_codes = tag.request_system_code()
    print "%d system code found." % len(system_codes)
    print system_codes

  def show_all_services(self, tag):
    print tag
    n = 32
    for i in xrange(0, 0x10000, n):
        self.check_services(tag, i, n)

  def call(self, func, timeout=0):
    if self.clf:
      self.clf.wait_card(func, timeout)
    else:
      print "ERROR: no NFC reader"
    
  def read_syscode(self, timeout=0):
    self.call(self.show_syscode, timeout)
      
  def dump_tag(self, timeout=0):
    self.call(self.show_tag_info, timeout)

  def print_id(self, timeout=0):
    self.call(self.print_tag_info, timeout)

  def info(self, timeout=0):
    if self.clf:
      return self.clf.wait_card(self.save_id, timeout)
    else:
      print "ERROR: no NFC reader"
    return False

  def save_id(self, tag):
    self.current_card_id=self.get_id(tag)

  def clear_id(self):
    self.current_card_id=None

  def is_registered(self):
    res=False
    if self.current_card_id in self.registeredCards:
       res=True
    self.clear_id()
    return res

#
#
# 
class Lock(threading.Thread):
  def __init__(self, pin=18, red_pin=24, green_pin=23, buzzer_pin=4, sw_pin=17):
    threading.Thread.__init__(self)
    self.config = ConfigParser.SafeConfigParser()

    self.state = None

    self.motor = ServoMotor()
    self.motor.setup(pin)

    self.red = Led(red_pin)
    self.green = Led(green_pin)
    self.buzzer = Buzzer(buzzer_pin)

    self.close()

    self.sw = Switch(sw_pin)
    self.nfc = NfcReader()

  def load_config(self, fname="autolock.conf"):
    self.config.read(fname)
    cards = self.get_value('nfc', 'cards', '')
    self.nfc.set_registered_cards(cards)

  def save_config(self, fname="autolock.conf"):
    self.config.write(fname)

  def set_value(self, sec, opt, val):
    try:
      self.config.set(sec, opt, val)
      return True
    except:
      return None
    
  def get_value(self, sec, opt, val):
    try:
      if self.config.has_option(sec, opt) :
        return self.config.get(sec, opt)
      else:
        return val
    except:
      return None

  def led_red(self):
    self.red.led_on()
    self.green.led_off()

  def led_green(self):
    self.red.led_off()
    self.green.led_on()

  def led_off(self):
    self.red.led_off()
    self.green.led_off()

  def open(self, pos=150):
    self.buzzer.pipo()
    self.motor.rotate(pos)
    self.led_green()
    self.state = 'Opened'

  def close(self, pos=50):
    self.buzzer.popi()
    self.motor.rotate(pos)
    self.led_red()
    self.state = 'Closed'

  def beep(self, tones):
    self.buzzer.beep(tones)

  def register_card(self):
    self.nfc.call(self.nfc.register_card)

  def wait_card(self, tout=0):
    res = self.nfc.info(tout)
    if res :
      if self.nfc.is_registered() :
        if self.state == 'Closed':
          print "Open !!"
          self.open()
        elif self.state == 'Opened':
          print "Close !!"
          self.close()
      else:
        print "You card is not registerd"
        self.buzzer.boo()

    return res

  def sw_push(self):
    print "Push switch"

  def start(self):
    self.sw.start(self.sw_push, self.stop)
    self.mainloop = True
    threading.Thread.start(self)

  def stop(self):
    self.mainloop = False
    self.sw.stop()

  def run(self):
    while self.mainloop:
      self.wait_card(1)
    
    self.led_off()
    print "Terminated" 

#
#
#
if __name__ == '__main__' :
  try:
    id    =  int(sys.argv[1])
    angle =  int(sys.argv[2])

    servo = ServoMotor() 
    servo.motor_main(id, angle)

  except:
    print "Usage: python %s PWM_ID Count" % sys.argv[0]

