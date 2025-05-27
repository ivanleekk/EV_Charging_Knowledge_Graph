import requests
from typing import Optional

def get_municipality_from_pc4_geocoding(pc4_code: str, api_key: str) -> Optional[str]:
    """
    Get municipality for PC4 code using the standard Geocoding API.
    
    Args:
        pc4_code (str): Dutch PC4 postal code
        api_key (str): Google Maps API key
        
    Returns:
        Optional[str]: Municipality name or None if not found
    """
    # First geocode the postal code to get coordinates
    geocode_url = "https://maps.googleapis.com/maps/api/geocode/json"
    
    params = {
        'address': f"{pc4_code}, Netherlands",
        'key': api_key
    }
    
    try:
        response = requests.get(geocode_url, params=params)
        response.raise_for_status()
        data = response.json()
        
        if data['status'] == 'OK' and data['results']:
            location = data['results'][0]['geometry']['location']
            lat, lng = location['lat'], location['lng']
            
            # Now reverse geocode to get administrative areas
            reverse_params = {
                'latlng': f"{lat},{lng}",
                'result_type': 'administrative_area_level_2',
                'key': api_key
            }
            
            reverse_response = requests.get(geocode_url, params=reverse_params)
            reverse_response.raise_for_status()
            reverse_data = reverse_response.json()
            
            if reverse_data['status'] == 'OK' and reverse_data['results']:
                for component in reverse_data['results'][0]['address_components']:
                    if 'administrative_area_level_2' in component['types']:
                        return component['long_name']
        
        return None
        
    except requests.exceptions.RequestException as e:
        print(f"Error querying Geocoding API: {e}")
        return None
