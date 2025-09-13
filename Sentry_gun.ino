#include <Stepper.h>

//Define pins for PIR sensors and ultrasonic sensor
#define PIR1 2
#define PIR2 3
#define PIR3 4
#define TRIGGER 6
#define ECHO 7

//Define stepper motor pins and settings
#define STEPPER_IN1 8
#define STEPPER_IN2 10
#define STEPPER_IN3 9
#define STEPPER_IN4 11
#define STEPS_PER_REV 2038
#define STEPPER_RPM 10

//Define switch pin
#define SWITCH 13

//Define variables
int pir1State = 0;
int pir2State = 0;
int pir3State = 0;
int ultrasonicDistance = 0;

//Initialize stepper motor
Stepper myStepper(STEPS_PER_REV, STEPPER_IN1, STEPPER_IN3, STEPPER_IN2, STEPPER_IN4);

void setup() {
  //Initialize serial communication
  Serial.begin(115200);

  //Set stepper motor speed
  myStepper.setSpeed(STEPPER_RPM);

  //Set switch pin as output
  pinMode(SWITCH, OUTPUT);

  //Clear serial monitor and print starting message
  Serial.println("Starting new run");
}

void loop() {
  //Clear all variables and readings
  pir1State = 0;
  pir2State = 0;
  pir3State = 0;
  ultrasonicDistance = 0;

  //Read state of PIR sensors
  pir1State = digitalRead(PIR1);
  pir2State = digitalRead(PIR2);
  pir3State = digitalRead(PIR3);

  //Read ultrasonic sensor
  ultrasonicDistance = readUltrasonic();

  //Print readings to serial monitor
  Serial.print("PIR1: ");
  Serial.print(pir1State);
  Serial.print(" PIR2: ");
  Serial.print(pir2State);
  Serial.print(" PIR3: ");
  Serial.print(pir3State);
  Serial.print(" Ultrasonic: ");
  Serial.println(ultrasonicDistance);

  //Check conditions for stepper motor movement and switch activation
  if (pir3State == HIGH && pir2State == LOW && pir1State == LOW) {
    //Move stepper motor counterclockwise 500 steps
    myStepper.step(-500);

    //Read ultrasonic sensor
    ultrasonicDistance = readUltrasonic();

    //Check if distance is below 50
    if (ultrasonicDistance < 50) {
      //Activate switch for 0.1 seconds
      digitalWrite(SWITCH, HIGH);
      delay(100);
      digitalWrite(SWITCH, LOW);
    }

    //Move stepper motor clockwise 500 steps
    myStepper.step(500);
  }
  else if (pir2State == HIGH && pir1State == LOW && pir3State == LOW) {
    //Move stepper motor clockwise 500 steps
    myStepper.step(500);

    //Read ultrasonic sensor
    ultrasonicDistance = readUltrasonic();

    //Check if distance is below 50
    if (ultrasonicDistance < 50) {
      //Activate switch for 0.1 seconds
      digitalWrite(SWITCH, HIGH);
      delay(100);
      digitalWrite(SWITCH, LOW);
    }

    //Move stepper motor counterclockwise 500 steps
    myStepper.step(-500);
  }
  else if (pir1State == HIGH && pir2State == LOW && pir3State == LOW && ultrasonicDistance < 50) {
    //Activate switch for 0.1 seconds
    digitalWrite(SWITCH, HIGH);
    delay(100);
    digitalWrite(SWITCH, LOW);
  }
  else {
    //Print "all clear" if no conditions are met
    Serial.println("all clear");
  }

  //Wait 3 seconds
  delay(3000);
}

//Function to read ultrasonic sensor
int readUltrasonic() {
  //Send ultrasonic pulse
  digitalWrite(TRIGGER, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIGGER, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIGGER, LOW);

  //Read echo pulse
  long duration = pulseIn(ECHO, HIGH);

  //Calculate distance in cm
  int distance = duration * 0.034 / 2;

  //Return distance value
  return distance;
}
