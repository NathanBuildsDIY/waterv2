import network
import socket
import time
import os
import machine
import ustruct
from machine import Pin, PWM
import _thread

# Function to check and create the schedule.txt file if it doesn't exist
def check_and_create_schedule_file():
    filename = "schedule.txt"
    
    # Check if the file exists using os.stat()
    try:
        os.stat(filename)  # Try to get file stats
        print(f"{filename} already exists. No need to create a new file.")
    except OSError:
        print(f"{filename} not found. Creating file and populating with default data.")
        
        # Create and write default rows to the file
        with open(filename, 'w') as f:
            f.write("row1, 7, 1, 7, 2, 1\n")
            f.write("row2, 7, 3, 7, 4, 1\n")
            f.write("row3, 7, 5, 7, 6, 1\n")
            f.write("row4, 7, 7, 7, 8, 1\n")
            f.write("row5, 7, 9, 7, 10, 1\n")
            f.write("row6, 7, 11, 7, 12, 1\n")
            f.write("row7, 7, 13, 7, 14, 1\n")
        print(f"{filename} created and populated with default data.")

# Function to handle setting the system time
def set_system_time(new_time):
    # Create an RTC object - this is so we can reset system time when not network connected
    rtc = machine.RTC()
    if new_time:
        # Extract hour and minute from new_time (e.g., "12:34")
        hours, minutes = map(int, new_time.split(":"))

        # Set the system time to a fixed date and the parsed time
        # Example: Set time to March 18, 2025, Tuesday, at the provided hour and minute
        rtc.datetime((2025, 3, 18, 2, hours, minutes, 0, 0))  # Set year, month, day, weekday, hours, minutes, seconds, subseconds
        print(f"Changing system time to: {new_time}")

def turn_on_city_supply(time_in_seconds):
  solenoid.duty_u16(65535) #turn on city supply. 
  sleep(time_in_seconds)
  pwm.duty_u16(0) #turn off city supply
  sleep(0.5)

def run_motor(zone,time_in_seconds):
  #set up selector servo in nanoseconds
  zone_selector = PWM(Pin(0), freq=50, duty_ns=380000)
  zone_ns = [390000, 660000, 980000, 1350000, 1670000, 1990000, 2300000, 2600000] #zone 0 = all zones off.
  zone_selector.duty_ns(zone_ns[0]) #turn off all zones
  pump = PWM(Pin(13), freq=50, duty_u16=0)
  #solenoid = PWM(Pin(18), freq=50, duty_u16=0) #to be added later
  zone_selector.duty_ns(zone_ns[int(zone)]) #set the servo to that zone
  time.sleep(2) #wait for servo arm to arrive
  pump.duty_u16(65535) #turn on the pump
  time.sleep(int(time_in_seconds))
  pump.duty_u16(0) #turn off the pump
  time.sleep(0.2) #break to no overload power supply
  zone_selector.duty_ns(zone_ns[0]) #turn off all zones
  time.sleep(1) #let arm return to normal
  zone_selector.deinit() #release pins
  pump.deinit() #release pins

def manual_url_decode(encoded_str):
    # Create a translation dictionary for URL encoding
    decode_map = {
        "%3A": ":",  # Colon
        "%2F": "/",  # Slash
        "%20": " ",  # Space
        "%3D": "=",  # Equals
        "%26": "&",  # Ampersand
        "%2C": ",",  # Comma
        "%2E": ".",  # Period
        # Add more mappings as needed
    }
    # Replace all occurrences of URL-encoded characters with their decoded counterparts
    for encoded, decoded in decode_map.items():
        encoded_str = encoded_str.replace(encoded, decoded)
    return encoded_str

# Function to serve the page and handle the form submission
def serve_page():
    # Configure the Raspberry Pi Pico W as an access point (AP)
    ap = network.WLAN(network.AP_IF)
    ap.active(True)

    # Set the AP configuration (SSID and password)
    ssid = "Pico_Hotspot"
    password = "password123"

    ap.config(essid=ssid, password=password)

    # Print IP address when the AP is ready
    while not ap.active():
        time.sleep(1)
    print('Access Point is active')
    print('Network config:', ap.ifconfig())

    addr = socket.getaddrinfo('0.0.0.0', 80)[0][-1]
    s = socket.socket()
    s.bind(addr)
    s.listen(1)
    print('Listening on', addr)
    
    # Check and create schedule.txt if necessary
    check_and_create_schedule_file()
    print("entering server while loop")
    
    # Set a timeout to make the socket non-blocking (e.g., 900ms)
    s.settimeout(0.9)
    
    while True:
        try:    
            cl, addr = s.accept()
            print('Client connected from', addr)
            cl.settimeout(5.0)
            
            # Receive request
            request = cl.recv(1024)
            print('Request:', request)

            # Check if it's a POST request for form submission
            if b"POST /submit_schedule" in request:
                # Extract the form data from the request
                data = parse_request(request)
                
                # Check for overlap
                if check_for_overlap(data):
                    response = """HTTP/1.1 200 OK
Content-Type: text/html; charset=utf-8
Connection: close

<!DOCTYPE html>
<html>
<head><title>Schedule Submission Error</title></head>
<body>
<h1>Schedule not accepted, two or more zones overlap. Only 1 zone may operate at a time.</h1>
<a href="/">Go back to Schedule Form</a>
</body>
</html>
"""
                else:
                    # Write the schedule data to a file
                    write_schedule_to_file(data)
                    response = """HTTP/1.1 200 OK
Content-Type: text/html; charset=utf-8
Connection: close

<!DOCTYPE html>
<html>
<head><title>Schedule Submitted</title></head>
<body>
<h1>Schedule Submitted Successfully!</h1>
<a href="/">Go back to Schedule Form</a>
</body>
</html>
"""
                cl.send(response)
                cl.close()                

            # Handle the change time request
            elif b"POST /change_time" in request:
                data = parse_request(request)
                new_time = data.get('new_time')
                if new_time:
                    set_system_time(manual_url_decode(new_time))  # Call function to set the time
                response = generate_schedule_form() #send back to the start
                cl.send(response)
                cl.close()

            # Handle the Instant Test
            elif b"POST /instant_test" in request:
              data = parse_request(request)
              # Access the zone and runtime from the 'instant_test' key in the data
              if "instant_test" in data:
                  zone = data["instant_test"].get("zone")
                  runtime = data["instant_test"].get("runtime")
                  # Ensure that zone and runtime are not None or empty
                  if zone is not None and runtime is not None:
                      print(f"Testing zone {zone} for {runtime} seconds")
                      run_motor(zone,runtime)
                      response = generate_schedule_form() #send back to the start
                      cl.send(response)
                      cl.close()
                  else:
                      print("Error: Invalid zone or runtime data")
              else:
                  print("Error: Instant test data not found")

            else:
                # Display the schedule form
                response = generate_schedule_form()
                cl.send(response)
                cl.close()
                
        except OSError as e:
            # Check if it was a timeout error (MicroPython raises OSError on timeout)
            if e.args[0] == 110:  # Timeout error code in MicroPython
                print("No client connected, continuing...")
            else:
                print(f"Unexpected error: {e}")
            
        #sadly, couldn't thread this. So we'll check if we should start a motor here
        current_time = time.localtime()
        current_seconds = current_time[5]
        if current_seconds % 5 == 0:
            check_schedule()
            time.sleep(1)
        time.sleep(0.1)

# Function to parse the POST request and extract the schedule data
def parse_request(request):
    # Split the request by line
    request = request.decode("utf-8")
    body = request.split("\r\n\r\n")[1]  # Extract the body of the request

    # Initialize a dictionary to store the parsed data
    data = {}

    # Extract the system time (if any)
    if "new_time=" in body:
        new_time = body.split("new_time=")[1].split("&")[0]  # Extract the new_time field value
        data["new_time"] = new_time

    # Extract the schedule data (start and stop times for each zone)
    for i in range(1, 8):
        # Extract the start and stop times for each zone
        start_time = body.split(f"start{i}=")[1].split("&")[0] if f"start{i}=" in body else "NULL"
        stop_time = body.split(f"stop{i}=")[1].split("&")[0] if f"stop{i}=" in body else "NULL"
        data[f"row{i}"] = {"start": start_time, "stop": stop_time}

    # Extract the instant test zone and runtime (if any)
    if "zone=" in body and "runtime=" in body:
        zone = body.split("zone=")[1].split("&")[0]  # Extract the selected zone for instant test
        runtime = body.split("runtime=")[1].split("&")[0]  # Extract the runtime for the instant test
        data["instant_test"] = {"zone": zone, "runtime": runtime}  # Add to instant_test dictionary

    return data

# Function to check for overlapping times
def check_for_overlap(data):
    time_windows = []
    
    # Gather start/stop times in the form of tuples (start, stop)
    for row, times in data.items():
        if times['start'] != "NULL" and times['stop'] != "NULL":
            start_time = times['start']
            stop_time = times['stop']
            time_windows.append((start_time, stop_time))
    
    # Check for overlap
    for i, (start1, stop1) in enumerate(time_windows):
        for j, (start2, stop2) in enumerate(time_windows):
            if i != j:  # Don't compare the same row
                # Convert times to minutes for easier comparison
                start1_minutes = convert_to_minutes(start1)
                stop1_minutes = convert_to_minutes(stop1)
                start2_minutes = convert_to_minutes(start2)
                stop2_minutes = convert_to_minutes(stop2)
                
                # Check if they overlap
                if (start1_minutes < stop2_minutes) and (start2_minutes < stop1_minutes):
                    return True  # Overlap detected
    
    return False  # No overlap detected

# Function to convert time "HH:MM" to minutes
def convert_to_minutes(time_str):
    # Decode the URL-encoded string (e.g., "10%3A13" to "10:13")
    time_str = manual_url_decode(time_str)
    hours, minutes = map(int, time_str.split(":"))
    return hours * 60 + minutes

# Function to write the schedule data to a file in the format: row, start hour, start minute, duration in minutes
def write_schedule_to_file(data):
    with open('schedule.txt', 'w') as f:
        for row, times in data.items():
            start_time = times['start']
            stop_time = times['stop']
            
            if start_time != "NULL" and stop_time != "NULL":
                try:
                    # Decode URL-encoded start and stop times (e.g., "10%3A12" -> "10:12")
                    start_time = manual_url_decode(start_time)
                    stop_time = manual_url_decode(stop_time)
                    
                    start_hour, start_minute = map(int, start_time.split(":"))
                    stop_hour, stop_minute = map(int, stop_time.split(":"))
                    
                    # Calculate the duration in minutes
                    start_in_minutes = start_hour * 60 + start_minute
                    stop_in_minutes = stop_hour * 60 + stop_minute
                    duration = stop_in_minutes - start_in_minutes
                    
                    # Write row, start hour, start minute, and duration
                    f.write(f"{row}, {start_hour}, {start_minute}, {stop_hour}, {stop_minute}, {duration}\n")
                except ValueError as e:
                    print(f"Error processing times for row {row}: {e}")
                    f.write(f"{row}, NULL, NULL, NULL, NULL, NULL\n")
            else:
                f.write(f"{row}, NULL, NULL, NULL, NULL, NULL\n")

# Function to read the schedule.txt file and return the schedule data
def read_schedule_from_file():
    schedule_data = {}
    try:
        with open('schedule.txt', 'r') as f:
            for line in f:
                # Each line is in the format: row, start_hour, start_minute, end_hour, end_minute, duration
                parts = line.strip().split(', ')
                if len(parts) == 6:
                    row = int(parts[0][3:])  # Extract the number from row1 -> 1, row2 -> 2, etc.
                    start_hour = int(parts[1])
                    start_minute = int(parts[2])
                    end_hour = int(parts[3])
                    end_minute = int(parts[4])
                    duration = int(parts[5])
                    schedule_data[row] = {
                        'start_hour': start_hour,
                        'start_minute': start_minute,
                        'end_hour': end_hour,
                        'end_minute': end_minute,
                        'duration': duration
                    }
    except OSError:
        # If the file doesn't exist, we return an empty schedule
        print("No schedule file found.")
    return schedule_data

# Function to generate the schedule form with pre-filled values
def generate_schedule_form():
    schedule_data = read_schedule_from_file()  # Read the schedule from file
    # Get the current system time (hour and minute)
    current_time = time.localtime()  # Get the current time in struct_time format
    formatted_time = "{:02}:{:02}".format(current_time[3], current_time[4])  # Format it as HH:MM

    # Generate form HTML
    form_html = f"""
<!DOCTYPE html>
<html>
<head><title>Set Schedule</title></head>
<style>
    .schedule-row {{
        display: flex;
        align-items: center;
        margin-bottom: 10px;
    }}
    .schedule-row label {{
        margin-right: 10px;
    }}
    .schedule-row input {{
        margin-right: 10px;
    }}
</style>
<body>
<h1>Set Schedule</h1>
<form method="POST" action="/change_time" onsubmit="return validateForm(event)">
    <!-- Current time section -->
    <div class="schedule-row">
        <label>Current System Time: </label>
        <input type="text" value="{formatted_time}" readonly>
        <label>Set Time: </label>
        <input type="time" name="new_time" required>
        <button type="submit" name="change_time">Change Time</button>
    </div>
</form>
<hr>

<form method="POST" action="/submit_schedule" onsubmit="return validateForm(event)">
    <!-- Schedule Section -->
    """
    
    # Generate 7 rows of start/stop time inputs with pre-filled values from schedule_data
    for i in range(1, 8):
        # Check if we have data for this row
        if i in schedule_data:
            start_hour = schedule_data[i]['start_hour']
            start_minute = schedule_data[i]['start_minute']
            end_hour = schedule_data[i]['end_hour']
            end_minute = schedule_data[i]['end_minute']
            start_time = f"{start_hour:02}:{start_minute:02}"  # Format time as HH:MM
            end_time = f"{end_hour:02}:{end_minute:02}"      # Format time as HH:MM
        else:
            # If no data, default to NULL
            start_time = "NULL"
            end_time = "NULL"

        # Group start and stop time fields on the same line using a flexbox layout
        form_html += f"""
        <div class="schedule-row">
            <label for="start{i}">Row {i} Start Time: </label>
            <input type="time" name="start{i}" value="{start_time}" required>
            <label for="stop{i}">Row {i} Stop Time: </label>
            <input type="time" name="stop{i}" value="{end_time}" required>
        </div>
        """
    
    form_html += """
    <!-- Submit Button -->
    <button type="submit" name="submit_schedule">Submit Schedule</button>
    <p><i>NOTE: To preserve pump health and prevent overheating, each zone will only pump 50% of the allotted window, plan windows accordingly</i></p>
    </form>

    <hr>

    <!-- Instant Test Section -->
    <form method="POST" action="/instant_test" onsubmit="return validateForm(event)">
    <div class="schedule-row">
        <label for="zone">Instant Test - Select Zone: </label>
        <select name="zone">
            <option value="1">Zone 1</option>
            <option value="2">Zone 2</option>
            <option value="3">Zone 3</option>
            <option value="4">Zone 4</option>
            <option value="5">Zone 5</option>
            <option value="6">Zone 6</option>
            <option value="7">Zone 7</option>
        </select>
        <label for="runtime">Run Time (seconds): </label>
        <input type="number" name="runtime" min="1" required>
        <button type="submit" name="instant_test">Run Test</button>
    </div>
    </form>

<script>
// Function to validate the form based on which button was clicked
function validateForm(event) {
    // Prevent form submission to handle validation first
    event.preventDefault();

    // Get the name of the button clicked
    let action = event.submitter.name;

    let valid = true;

    // Handle "Set Time" button validation
    if (action === 'change_time') {
        const timeInput = document.querySelector('[name="new_time"]');
        if (!timeInput.value) {
            alert('Please set the system time.');
            valid = false;
        }
    }

    // Handle "Submit Schedule" button validation
    if (action === 'submit_schedule') {
        const startInputs = document.querySelectorAll('input[name^="start"]');
        const stopInputs = document.querySelectorAll('input[name^="stop"]');
        startInputs.forEach((input, index) => {
            if (!input.value || !stopInputs[index].value) {
                alert('Please fill in all schedule times.');
                valid = false;
            }
        });
    }

    // Handle "Instant Test" button validation
    if (action === 'instant_test') {
        const runtimeInput = document.querySelector('[name="runtime"]');
        if (!runtimeInput.value) {
            alert('Please enter the run time.');
            valid = false;
        }
    }

    // If the form is valid, submit it
    if (valid) {
        event.target.submit();
    }
}
</script>

</body>
</html>
    """
    return form_html

def check_schedule():
        print("Starting schedule check...")
        #while True:
        # Read the schedule file
        schedule_data = read_schedule_from_file()

        # Get the current system time (hour and minute)
        current_time = time.localtime()  # Get the current time in struct_time format
        current_hour = current_time[3]
        current_minute = current_time[4]
        print(f"Current time: {current_hour}:{current_minute}")

        # Loop through each zone's schedule
        for row, times in schedule_data.items():
            start_hour = times['start_hour']
            start_minute = times['start_minute']
            duration = times['duration']  # Assume duration is in minutes

            print(f"Checking zone {row}: {start_hour}:{start_minute}")

            # Check if the current time matches the start time for this zone
            if current_hour == start_hour and current_minute == start_minute:
                # Trigger the zone to start for the given duration
                print(f"Starting zone {row} for {duration} minutes at {current_hour}:{current_minute}")
                run_motor(row,int(duration)*60)

        # Wait for 60 seconds before checking again
        #print("Waiting for next schedule check...")
        #time.sleep(60)

'''
#threading seems to fail. Forget it and instead include checking start of schedule in webserver. It will block :(
# Start the schedule check function on core 1
print("starting schedule thread on core 1")
_thread.start_new_thread(check_schedule, ())

# Start the web server on core 0
print("starting server thread on core 0")
serve_page()
'''
serve_page()