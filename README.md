# 🚑 AI Disaster Response Planner

An intelligent desktop application that simulates emergency response in disaster scenarios using classical Artificial Intelligence algorithms.

---

## 📌 Overview

This project models a real-world earthquake scenario where:

* 🚑 Ambulances must navigate a city
* ⚠️ Multiple injured people need urgent help
* 🚧 Roads may be blocked
* 🏥 Hospitals have limited capacity

The system uses AI techniques to make optimal decisions in real time to **maximize the number of saved lives**.

---
## 🧠 AI Techniques Used

### 1. A* Search Algorithm

* Finds the shortest and safest path for ambulances
* Avoids blocked roads
* Dynamically recalculates routes

### 2. Constraint Satisfaction Problem (CSP)

* Assigns injured people to hospitals
* Respects hospital capacity constraints

### 3. Multi-Objective Heuristic

Combines:

* Distance
* Injury severity
* Hospital load

```python
Score = distance + (severity_weight * severity) + (hospital_load_weight * hospital_load)
```

---

## 🎮 Features

* 🗺️ Interactive grid-based city map
* 🚑 Real-time ambulance movement
* ⚠️ Dynamic incident generation
* 🚧 Road blocking/unblocking
* 🔄 Dynamic AI replanning
* 🎛️ Simulation control (Start / Pause / Reset)
* ⚡ Speed control (Slow / Normal / Fast)

---

## 📊 Dashboard

Real-time analytics including:

* ❤️ Lives Saved
* ⏱️ Average Response Time
* 🚑 Completed Missions
* 📈 Efficiency Percentage

---

## 🎬 Demo Mode

A special mode for presentations:

* Automatically runs simulation
* Shows AI decisions
* Visualizes pathfinding (A*)
* Demonstrates resource allocation (CSP)

---

## 🧩 Project Structure

```
project/
│
├── algorithms.py   # AI logic (A*, CSP, Heuristic)
├── simulation.py   # Environment & data generation
├── ui.py           # Desktop UI (Tkinter / PyQt)
├── main.py         # Entry point
```

---

## ⚙️ Installation

### 1. Clone the repository

```bash
git clone https://github.com/your-username/ai-disaster-response.git
cd ai-disaster-response
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Run the application

```bash
python main.py
```

---

## 🧪 How It Works

1. The map is represented as a grid (graph)
2. AI selects the best ambulance based on heuristic scoring
3. A* calculates the optimal route
4. CSP assigns the patient to a suitable hospital
5. The system updates results in real time

---

## 🎯 Purpose

This project demonstrates how classical AI techniques can be applied to solve:

* Resource allocation problems
* Pathfinding challenges
* Real-time decision-making scenarios

---

## 🧠 Key Learning Outcomes

* Practical understanding of A* search
* Applying CSP in real-world scenarios
* Designing multi-objective heuristics
* Building interactive AI systems

---

## 📸 Screenshots

> Add screenshots of your application here

---

## 🚀 Future Improvements

* Machine Learning-based prediction
* Real-world map integration
* Multi-agent coordination
* Web-based version

---

## 👨‍💻 Creative Minds

**Hamza ibrahim  **

Computer Science Student | AI Enthusiast

---

## ⭐ Note

This project bridges the gap between **theoretical AI concepts** and **real-world applications** through visualization and simulation.
# 🚑 AI Disaster Response Planner

An intelligent desktop application that simulates emergency response in disaster scenarios using classical Artificial Intelligence algorithms.

---

## 📌 Overview

This project models a real-world earthquake scenario where:

* 🚑 Ambulances must navigate a city
* ⚠️ Multiple injured people need urgent help
* 🚧 Roads may be blocked
* 🏥 Hospitals have limited capacity

The system uses AI techniques to make optimal decisions in real time to **maximize the number of saved lives**.

---
## 🧠 AI Techniques Used

### 1. A* Search Algorithm

* Finds the shortest and safest path for ambulances
* Avoids blocked roads
* Dynamically recalculates routes

### 2. Constraint Satisfaction Problem (CSP)

* Assigns injured people to hospitals
* Respects hospital capacity constraints

### 3. Multi-Objective Heuristic

Combines:

* Distance
* Injury severity
* Hospital load

```python
Score = distance + (severity_weight * severity) + (hospital_load_weight * hospital_load)
```

---

## 🎮 Features

* 🗺️ Interactive grid-based city map
* 🚑 Real-time ambulance movement
* ⚠️ Dynamic incident generation
* 🚧 Road blocking/unblocking
* 🔄 Dynamic AI replanning
* 🎛️ Simulation control (Start / Pause / Reset)
* ⚡ Speed control (Slow / Normal / Fast)

---

## 📊 Dashboard

Real-time analytics including:

* ❤️ Lives Saved
* ⏱️ Average Response Time
* 🚑 Completed Missions
* 📈 Efficiency Percentage

---

## 🎬 Demo Mode

A special mode for presentations:

* Automatically runs simulation
* Shows AI decisions
* Visualizes pathfinding (A*)
* Demonstrates resource allocation (CSP)

---

## 🧩 Project Structure

```
project/
│
├── algorithms.py   # AI logic (A*, CSP, Heuristic)
├── simulation.py   # Environment & data generation
├── ui.py           # Desktop UI (Tkinter / PyQt)
├── main.py         # Entry point
```

---

## ⚙️ Installation

### 1. Clone the repository

```bash
git clone https://github.com/your-username/ai-disaster-response.git
cd ai-disaster-response
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Run the application

```bash
python main.py
```

---

## 🧪 How It Works

1. The map is represented as a grid (graph)
2. AI selects the best ambulance based on heuristic scoring
3. A* calculates the optimal route
4. CSP assigns the patient to a suitable hospital
5. The system updates results in real time

---

## 🎯 Purpose

This project demonstrates how classical AI techniques can be applied to solve:

* Resource allocation problems
* Pathfinding challenges
* Real-time decision-making scenarios

---

## 🧠 Key Learning Outcomes

* Practical understanding of A* search
* Applying CSP in real-world scenarios
* Designing multi-objective heuristics
* Building interactive AI systems

---

## 📸 Screenshots

> Add screenshots of your application here

---

## 🚀 Future Improvements

* Machine Learning-based prediction
* Real-world map integration
* Multi-agent coordination
* Web-based version

---

## 👨‍💻 Creative Minds

**Hamza ibrahim **
**hanan waled **
**khaled gamal **

Computer Science Student | AI Enthusiast

---

## ⭐ Note

This project bridges the gap between **theoretical AI concepts** and **real-world applications** through visualization and simulation.
