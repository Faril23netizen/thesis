#!/usr/bin/env python3
"""
homeassistant_bridge.py - Home Assistant IoT Bridge
====================================================
Mengambil data sensor dari Home Assistant untuk perbandingan
Edge AI (N3IWF) vs Cloud IoT (Home Assistant).

Home Assistant REST API:
  GET /api/states/<entity_id>
  Headers: Authorization: Bearer <token>

Setup:
  1. Buat Long-Lived Access Token di Home Assistant
  2. Edit config di bawah dengan URL & token Anda
  3. Pastikan sensor pH & suhu sudah terdaftar di HA

Usage:
  from homeassistant_bridge import HomeAssistantBridge
  
  ha = HomeAssistantBridge(url="http://192.168.1.100:8123", token="your_token")
  pH, temp = ha.get_sensor_data()
"""

import time
import requests
from typing import Tuple, Optional


class HomeAssistantBridge:
    """Bridge untuk mengambil data sensor dari Home Assistant."""
    
    def __init__(self, url: str, token: str, 
                 ph_entity: str = "sensor.aquaculture_ph",
                 temp_entity: str = "sensor.aquaculture_temperature"):
        """
        Args:
            url: Home Assistant URL (e.g., http://192.168.1.100:8123)
            token: Long-Lived Access Token dari HA
            ph_entity: Entity ID untuk sensor pH
            temp_entity: Entity ID untuk sensor suhu
        """
        self.url = url.rstrip('/')
        self.token = token
        self.ph_entity = ph_entity
        self.temp_entity = temp_entity
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        self.timeout = 5  # seconds
        
    def get_state(self, entity_id: str) -> Optional[dict]:
        """Get state dari entity Home Assistant."""
        try:
            response = requests.get(
                f"{self.url}/api/states/{entity_id}",
                headers=self.headers,
                timeout=self.timeout
            )
            if response.status_code == 200:
                return response.json()
            else:
                print(f"[HA] Error {response.status_code}: {response.text}")
                return None
        except requests.exceptions.RequestException as e:
            print(f"[HA] Connection error: {e}")
            return None
    
    def get_sensor_data(self) -> Tuple[Optional[float], Optional[float], float]:
        """
        Ambil data pH & suhu dari Home Assistant.
        
        Returns:
            (pH, temperature, latency_ms)
            pH dan temperature bisa None jika gagal
        """
        start_time = time.perf_counter()
        
        # Get pH
        ph_state = self.get_state(self.ph_entity)
        pH = None
        if ph_state and ph_state.get("state") not in ["unavailable", "unknown"]:
            try:
                pH = float(ph_state["state"])
            except (ValueError, TypeError):
                pass
        
        # Get Temperature
        temp_state = self.get_state(self.temp_entity)
        temp = None
        if temp_state and temp_state.get("state") not in ["unavailable", "unknown"]:
            try:
                temp = float(temp_state["state"])
            except (ValueError, TypeError):
                pass
        
        latency_ms = (time.perf_counter() - start_time) * 1000
        return pH, temp, latency_ms
    
    def send_action(self, action: str) -> bool:
        """
        (Optional) Kirim action ke Home Assistant untuk kontrol aerator.
        
        Args:
            action: "OFF", "LOW", "MED", "HIGH"
        
        Returns:
            True jika berhasil
        """
        # Mapping action ke service call HA
        service_map = {
            "OFF":  {"domain": "switch", "service": "turn_off", "entity": "switch.aerator"},
            "LOW":  {"domain": "fan", "service": "set_percentage", "entity": "fan.aerator", "data": {"percentage": 33}},
            "MED":  {"domain": "fan", "service": "set_percentage", "entity": "fan.aerator", "data": {"percentage": 66}},
            "HIGH": {"domain": "fan", "service": "set_percentage", "entity": "fan.aerator", "data": {"percentage": 100}},
        }
        
        if action not in service_map:
            return False
        
        svc = service_map[action]
        try:
            payload = {
                "entity_id": svc["entity"]
            }
            if "data" in svc:
                payload.update(svc["data"])
            
            response = requests.post(
                f"{self.url}/api/services/{svc['domain']}/{svc['service']}",
                headers=self.headers,
                json=payload,
                timeout=self.timeout
            )
            return response.status_code == 200
        except requests.exceptions.RequestException as e:
            print(f"[HA] Action error: {e}")
            return False
    
    def test_connection(self) -> bool:
        """Test koneksi ke Home Assistant."""
        try:
            response = requests.get(
                f"{self.url}/api/",
                headers=self.headers,
                timeout=self.timeout
            )
            if response.status_code == 200:
                data = response.json()
                print(f"[HA] Connected to Home Assistant: {data.get('message', 'OK')}")
                return True
            else:
                print(f"[HA] Connection failed: {response.status_code}")
                return False
        except requests.exceptions.RequestException as e:
            print(f"[HA] Connection error: {e}")
            return False


# ── Example Usage ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # EDIT INI SESUAI SETUP HOME ASSISTANT ANDA
    HA_URL = "http://192.168.1.100:8123"
    HA_TOKEN = "your_long_lived_access_token_here"
    
    ha = HomeAssistantBridge(
        url=HA_URL,
        token=HA_TOKEN,
        ph_entity="sensor.aquaculture_ph",
        temp_entity="sensor.aquaculture_temperature"
    )
    
    # Test connection
    if ha.test_connection():
        # Get sensor data
        pH, temp, latency = ha.get_sensor_data()
        print(f"[HA] pH={pH}, Temp={temp}°C, Latency={latency:.2f}ms")
        
        # (Optional) Send action
        # ha.send_action("MED")
    else:
        print("[HA] Failed to connect to Home Assistant")
