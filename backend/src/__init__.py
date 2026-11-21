"""
FuelFlux Backward-Compatibility Module.
Maps legacy 'src.*' imports directly to the consolidated 'app.*' package.
"""
import sys
import app

# Re-export app as src
sys.modules['src'] = app
