<h1 align = 'center'>GREMNIN</h1>


The application plots a satellite's orbit with points around the world map based on the TLE, sampling rate, start time, and length of simulation, along with a 200km by 200km box about each point where the satellite can scan. It also provides a live location update of the satellite in real time. 

An option is also provided whether to simulate the orbit on a 2D map or around a 3D globe. The 3D globe also has the same features as the 2D map.

Additionally, it checks whether the satellite can scan over a point that is specified by the user

Follow the instructions in this file to run the code

All the required libraries are in "requirements.txt"

# Steps to run the project


Make sure to create a virtual environment before importing any new libraries

First run this to create the virtual environment

```bash
python -m venv newenv #newenv is the name of the virtual environment
```

Then run this to activate your virtual environment

On windows Command Prompt - 
```bash
newenv\Scripts\activate.bat 
```

On windows PowerShell - 

```bash
newenv\Scripts\Activate.ps1
```

On MacOS/Linux

```bash
source newenv/bin/activate
```

Run this in the terminal to import all necessary libraries before running the code


```bash
pip install -r requirements.txt
```
or if it doesn't work

```bash
pip3 install -r requirements.txt
```


Run frontend.py

