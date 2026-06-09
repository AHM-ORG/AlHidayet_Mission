import glob
import re

# Pages with the main-header logo (non-dashboard pages)
files = glob.glob('templates/*.html')

count = 0
for filepath in files:
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        if 'main-header' not in content:
            continue
            
        # Check if logo image already exists
        if 'logo-img' in content or 'logo_url' in content:
            continue
        
        # Add logo image before the logo-text span
        old = '<span class="logo-text">Al Hidayet <span class="highlight">Mission</span></span>'
        new = '<img src="{{ logo_url }}" alt="AHM" style="width:36px; height:36px; border-radius:8px; object-fit:cover;">\n                    <span class="logo-text">Al Hidayet <span class="highlight">Mission</span></span>'
        
        if old in content:
            content = content.replace(old, new, 1)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            count += 1
            print(f"Updated: {filepath}")
    except Exception as e:
        print(f"Error on {filepath}: {e}")

print(f"\nTotal files updated: {count}")
