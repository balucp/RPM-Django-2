#!/bin/bash
# Generate NOTICE file with license information

echo "NOTICE" > NOTICE
echo "# This file is generated using pip-licenses to identify and document third-party package licenses for copyright attribution" >> NOTICE
echo "" >> NOTICE

# Create temporary virtual environment
python3 -m venv temp_venv
source temp_venv/bin/activate

# Install pip-licenses if not already installed
pip install pip-licenses

# Install from requirements file in current directory
pip install -r requirements.txt

# Generate license info
pip-licenses --format=plain >> NOTICE

# Cleanup
deactivate
rm -rf temp_venv
echo "NOTICE file generated successfully."