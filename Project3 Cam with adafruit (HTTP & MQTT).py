import time
import board
import busio
import adafruit_ov2640
import wiznet
import digitalio
import binascii
import gc
import ssl
from adafruit_wiznet5k.adafruit_wiznet5k import WIZNET5K
import adafruit_wiznet5k.adafruit_wiznet5k_socketpool as socketpool

# MQTT
import adafruit_minimqtt.adafruit_minimqtt as MQTT

# HTTP
from adafruit_io.adafruit_io import IO_HTTP
import adafruit_requests

try:
    from secrets import secrets
except ImportError:
    print("MQTT secrets are kept in secrets.py, please add them there!")
    raise


aio_username = secrets["aio_username"]
aio_key = secrets["aio_key"]

MY_MAC = "00:01:02:03:04:05"
IP_ADDRESS = (192, 168, 1, 100)
SUBNET_MASK = (255, 255, 255, 0)
GATEWAY_ADDRESS = (192, 168, 1, 1)
DNS_SERVER = (8, 8, 8, 8)

ethernetRst = digitalio.DigitalInOut(board.W5K_RST)
ethernetRst.direction = digitalio.Direction.OUTPUT

 
cs = digitalio.DigitalInOut(board.W5K_CS)

spi_bus = wiznet.PIO_SPI(board.W5K_SCK, 
                     quad_io0=board.W5K_MOSI, 
                     quad_io1=board.W5K_MISO, 
                     quad_io2=board.W5K_IO2, 
                     quad_io3=board.W5K_IO3)

print("reset")
ethernetRst.value = False
time.sleep(1)
ethernetRst.value = True

eth = WIZNET5K(spi_bus, cs, is_dhcp=True, mac=MY_MAC, debug=False)
print("Chip Version:", eth.chip)
print("MAC Address:", [hex(i) for i in eth.mac_address])
print("My IP address is:", eth.pretty_ip(eth.ip_address))

pool = socketpool.SocketPool(eth)

# Camera setup
i2c = busio.I2C(board.GP9, board.GP8)
cam = adafruit_ov2640.OV2640(
    i2c,
    data_pins=[board.GP0, board.GP1, board.GP2, board.GP3,
              board.GP4, board.GP5, board.GP6, board.GP7],
    clock=board.GP10,
    vsync=board.GP12,
    href=board.GP11,
    reset=board.GP13,
)

cam.size = adafruit_ov2640.OV2640_SIZE_VGA  # Smaller for memory
cam.colorspace = adafruit_ov2640.OV2640_COLOR_JPEG
time.sleep(2)



Mode = input("HTTP or MQTT? ").strip().upper()
# Initialize client based on mode
if Mode == "HTTP":
    ssl_context = ssl.create_default_context()
    requests = adafruit_requests.Session(pool, ssl_context)
    http_io = IO_HTTP(aio_username, aio_key, requests)
    print("HTTP ready")
elif Mode == "MQTT":
    mqtt_client = MQTT.MQTT(
        broker="io.adafruit.com",
        username=aio_username,
        password=aio_key,
        socket_pool=pool,
        is_ssl=False,
    )
    mqtt_client.connect()
    img_feed = aio_username + "/feeds/img"
    print("MQTT connected")
else:
    print("Invalid mode")
    while True: time.sleep(1)

buffer_size = 15000  # Start small

while True:
    try:
        buf = bytearray(buffer_size)
        img = cam.capture(buf)
        
        if img and len(img) > 100:
            print(f"Captured: {len(img)} bytes")
            encoded = binascii.b2a_base64(img).strip()
            
            if Mode == "MQTT":
                mqtt_client.publish(img_feed, encoded)
            else:
                http_io.send_data("img", encoded.decode('utf-8'))
                
            # Increase buffer if successful
            if len(img) > buffer_size - 1000:
                buffer_size = min(buffer_size + 2000, 25000)
                
        del img, buf, encoded
        gc.collect()
        
    except MemoryError:
        print("Memory error - reducing buffer")
        buffer_size = max(10000, buffer_size - 5000)
        gc.collect()
    except Exception as e:
        print(f"Error: {e}")
    
    time.sleep(3)