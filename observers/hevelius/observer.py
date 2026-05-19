#!/usr/bin/env python3
"""
JOHANNES HEVELIUS - The Cartographer

Mission: Map everything in the sky, build trajectory databases
Method: Positional astronomy, sky atlas generation
Output: Maps, charts, trajectory catalogs
"""
import json
import os
from datetime import datetime
import ephem

class Hevelius:
    """The Mapmaker - Everything has a position"""
    
    def __init__(self, config_file="/mnt/SYSTEM_ARCHIVE/OBSERVATORY/config.json"):
        with open(config_file) as f:
            config = json.load(f)
        
        self.location = config['location']
        self.name = "Hevelius"
        self.role = "Cartographer"
        
    def observe(self):
        """Create positional catalog for tonight"""
        
        # Set up observer location
        obs = ephem.Observer()
        obs.lat = str(self.location['latitude'])
        obs.lon = str(self.location['longitude'])
        obs.elevation = self.location['elevation_m']
        obs.date = datetime.utcnow()
        
        catalog = {
            'observer': 'Hevelius',
            'time': datetime.now().isoformat(),
            'location': self.location['name'],
            'celestial_positions': {}
        }
        
        # Map major celestial objects
        bodies = {
            'Sun': ephem.Sun(),
            'Moon': ephem.Moon(),
            'Venus': ephem.Venus(),
            'Mars': ephem.Mars(),
            'Jupiter': ephem.Jupiter(),
            'Saturn': ephem.Saturn()
        }
        
        for name, body in bodies.items():
            body.compute(obs)
            catalog['celestial_positions'][name] = {
                'altitude': f"{float(body.alt) * 180/3.14159:.2f}°",
                'azimuth': f"{float(body.az) * 180/3.14159:.2f}°",
                'visible': float(body.alt) > 0
            }
        
        return catalog
    
    def report(self, catalog):
        """Generate Hevelius's map report"""
        report = f"\n[{self.name}] Sky Map for {catalog['location']}:\n"
        
        visible = [name for name, data in catalog['celestial_positions'].items() if data['visible']]
        
        if visible:
            report += f"  Visible objects: {', '.join(visible)}\n"
            for name in visible:
                data = catalog['celestial_positions'][name]
                report += f"    {name}: Alt {data['altitude']}, Az {data['azimuth']}\n"
        else:
            report += "  No major celestial objects currently visible.\n"
        
        return report

if __name__ == "__main__":
    hevelius = Hevelius()
    catalog = hevelius.observe()
    print(hevelius.report(catalog))
    
    # Save map
    output_dir = "/mnt/SYSTEM_ARCHIVE/OBSERVATORY/observers/hevelius"
    os.makedirs(output_dir, exist_ok=True)
    
    with open(f"{output_dir}/sky_map_{datetime.now().strftime('%Y%m%d_%H%M')}.json", 'w') as f:
        json.dump(catalog, f, indent=2)
