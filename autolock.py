#!/usr/bin/python
# -*- coding: utf-8 -*-
#
import sys
import time
import ConfigParser

import wiringpi

import nfc
from binascii import hexlify

#
#  Servo Motor Control
#
alreadyInit = False

class ServoMotor:
  def __init__(self):
    self.readyGpio = alreadyInit
    self.PWM_PIN=[18, 13]
    self.pwm_range = 1920
    self.pwm_clock = 200

  def initGpio(self):
    if self.readyGpio == False:
      wiringpi.wiringPiSetupGpio()
      self.readyGpio = True

  def setup(self,id):
    self.initGpio()
    if id in self.PWM_PIN:
      self.setupPwm(id)
    else:
     self.setupSoftPwm(id)

  def setupPwm(self, id):
    wiringpi.pinMode(id, wiringpi.GPIO.PWM_OUTPUT)
    wiringpi.pwmSetMode(wiringpi.GPIO.PWM_MODE_MS)
    wiringpi.pwmSetRange(self.pwm_range)
    wiringpi.pwmSetClock(self.pwm_clock)

  def setupSoftPwm(self,id):
    wiringpi.pinMode(id, wiringpi.GPIO.PWM_OUTPUT)
    wiringpi.softPwmCreate(id, 0, self.pwm_clock/2)

  def pwmWrite(self, id, angle):
    if id in self.PWM_PIN:
      wiringpi.pwmWrite(id, angle)
    else:
      wiringpi.softPwmWrite(id, angle/10)

  def rotate(self, id, angle):
    self.pwmWrite(id, angle)
    if angle > 0:
      time.sleep(0.6)
      self.pwmWrite(id, 0)

  def motor_main(id, angle):
    motor = ServoMotor()
    motor.setup(id)
    motor.rotate(id, angle)

#
#  NFC
#
class NfcReader:
  def __init__(self):
    self.open_device()
    self.registeredCards = []
    self.clear_id()

  def open_device(self, typ='usb'):
    try:
      self.clf = nfc.ContactlessFrontend(typ)
    except:
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
    print tag._product
    print hexlify(tag.pmm)
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

  def call(self, func):
    if self.clf:
      self.clf.connect(rdwr={'on-connect': func})
    else:
      print "ERROR: no NFC reader"
    
  def read_syscode(self):
    self.call(self.show_syscode)
      
  def dump_tag(self):
    self.call(self.show_tag_info)

  def info(self):
    if self.clf:
      self.clf.connect(rdwr={'on-connect': self.save_id})

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
class Lock:
  def __init__(self, pin=18, red_pin=24, green_pin=23, tone_pin=4):
    self.config = ConfigParser.SafeConfigParser()
    self.motor_pin = pin
    self.red = red_pin
    self.green = green_pin
    self.tone = tone_pin
    self.state = None
    self.pipo = [500,1000]
    self.popi = [1000,500]
    self.boo = [500,0,500,500]

    self.motor = ServoMotor()
    self.motor.setup(pin)

    wiringpi.pinMode(self.red, wiringpi.GPIO.OUTPUT)
    wiringpi.pinMode(self.green, wiringpi.GPIO.OUTPUT)

    wiringpi.pinMode(self.tone, wiringpi.GPIO.OUTPUT)
    wiringpi.softToneCreate(self.tone)

    self.close()

    self.nfc = NfcReader()

  def load_config(self, fname="autolock.conf"):
    self.config.read(fname)

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
    wiringpi.digitalWrite(self.red, 1)
    wiringpi.digitalWrite(self.green, 0)

  def led_green(self):
    wiringpi.digitalWrite(self.red, 0)
    wiringpi.digitalWrite(self.green, 1)

  def led_off(self):
    wiringpi.digitalWrite(self.red, 0)
    wiringpi.digitalWrite(self.green, 0)

  def open(self, pos=150):
    self.beep(self.pipo)
    self.motor.rotate(self.motor_pin, pos)
    self.led_green()
    self.state = 'Opened'

  def close(self, pos=50):
    self.beep(self.popi)
    self.motor.rotate(self.motor_pin, pos)
    self.led_red()
    self.state = 'Closed'

  def beep(self, tones):
    for hz in tones:
      wiringpi.softToneWrite(self.tone, hz)
      time.sleep(0.1)
    wiringpi.softToneWrite(self.tone, 0)

  def register_card(self):
    self.nfc.call(self.nfc.register_card)

  def wait_card(self):
    self.nfc.info()
    if self.nfc.is_registered() :
      if self.state == 'Closed':
        print "Open !!"
        self.open()
      elif self.state == 'Opened':
        print "Close !!"
        self.close()
    else:
      print "You card is not registerd"
      self.beep(self.boo)

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

