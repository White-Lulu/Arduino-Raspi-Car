#include <AFMotor.h>
#include <Servo.h>

AF_DCMotor motorLeftFront(1);  // 左前 (M1)
AF_DCMotor motorLeftRear(2);   // 左后 (M2)
AF_DCMotor motorRightFront(3); // 右前 (M3)
AF_DCMotor motorRightRear(4);  // 右后 (M4)

Servo servo;
const int SERVO_PIN = 9;
const int TRIG_PIN = 2; 
const int ECHO_PIN = A0;

#define SPEED_STRAIGHT 150 // 直行速度 
#define SPEED_TURN 180     // 转向速度 (需要大一点扭力)

// 启动时的"猛冲"设置，防止低速启动摩擦力过大
#define KICK_SPEED 255
#define KICK_DURATION 20 // 缩短时间，反应更灵敏

// --- 辅助函数 ---

void motorsStop() {
  motorLeftFront.run(RELEASE);
  motorLeftRear.run(RELEASE);
  motorRightFront.run(RELEASE);
  motorRightRear.run(RELEASE);
}

void setAllSpeeds(uint8_t speed) {
  motorLeftFront.setSpeed(speed);
  motorLeftRear.setSpeed(speed);
  motorRightFront.setSpeed(speed);
  motorRightRear.setSpeed(speed);
}

void motorsForward(uint8_t speed) {
  setAllSpeeds(KICK_SPEED);
  
  // 左侧前进
  motorLeftFront.run(FORWARD); 
  motorLeftRear.run(FORWARD);
  
  // 右侧前进
  motorRightFront.run(BACKWARD);
  motorRightRear.run(BACKWARD);
  
  delay(KICK_DURATION);
  setAllSpeeds(speed);
}

void motorsBackward(uint8_t speed) {
  setAllSpeeds(KICK_SPEED);
  
  // 左侧后退
  motorLeftFront.run(BACKWARD); 
  motorLeftRear.run(BACKWARD);
  
  // 右侧后退
  motorRightFront.run(FORWARD); // 修正点：反向逻辑
  motorRightRear.run(FORWARD);  // 修正点
  
  delay(KICK_DURATION);
  setAllSpeeds(speed);
}

// 左转：左轮后退，右轮前进
void motorsTurnLeft(uint8_t speed) {
  setAllSpeeds(KICK_SPEED);
  
  motorLeftFront.run(BACKWARD);
  motorLeftRear.run(BACKWARD);
  
  motorRightFront.run(BACKWARD); 
  motorRightRear.run(BACKWARD);  
  
  delay(KICK_DURATION);
  setAllSpeeds(speed);
}

// 右转：左轮前进，右轮后退
void motorsTurnRight(uint8_t speed) {
  setAllSpeeds(KICK_SPEED);
  
  motorLeftFront.run(FORWARD);
  motorLeftRear.run(FORWARD);
  
  motorRightFront.run(FORWARD);
  motorRightRear.run(FORWARD);  
  
  delay(KICK_DURATION);
  setAllSpeeds(speed);
}

// 超声波测距函数
long readDistance() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);
  long duration = pulseIn(ECHO_PIN, HIGH, 30000); // 30ms超时，防止卡死
  if (duration == 0) return 999; // 超时视为空旷
  return duration * 0.034 / 2;
}

void setup() {
  Serial.begin(9600); 
  
  servo.attach(SERVO_PIN);
  servo.write(90);
  
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);

  motorsStop();
}

void loop() {
  if (Serial.available()) {
    char command = Serial.read(); 

    switch (command) {
      // 电机控制
      case 'F': motorsForward(SPEED_STRAIGHT); break;
      case 'B': motorsBackward(SPEED_STRAIGHT); break;
      case 'L': motorsTurnLeft(SPEED_TURN); break;
      case 'R': motorsTurnRight(SPEED_TURN); break;
      case 'S': motorsStop(); break;

      // 舵机控制
      case 'G': servo.write(90); break;  // 中
      case 'H': servo.write(180); break; // 左/右极限
      case 'J': servo.write(0); break;   // 右/左极限

      // 传感器控制 
      case 'U': { // 加上大括号以定义局部变量
        long dist = readDistance();
        Serial.print("Distance:");
        Serial.println(dist);
        break;
      }

      default:
        // motorsStop(); // 收到未知命令是否停车
        break;
    }
  }
}
