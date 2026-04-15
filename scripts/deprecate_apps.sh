#!/bin/bash
# Script to move duplicate apps to deprecated folder
# Run from /home/graco/WORK/server

set -e

echo "======================================"
echo "Moving Duplicate Apps to Deprecated"
echo "======================================"

# Create deprecated folder
mkdir -p apps/deprecated

# List of apps to deprecate
APPS=(
    "commerce"
    "messenger" 
    "messaging_v2"
    "marketing_v2"
    "core_v2"
)

echo ""
echo "Apps to be moved:"
for app in "${APPS[@]}"; do
    echo "  - $app"
done

echo ""
read -p "Are you sure you want to move these apps? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo "Cancelled."
    exit 0
fi

# Move each app
for app in "${APPS[@]}"; do
    if [ -d "apps/$app" ]; then
        echo "Moving apps/$app to apps/deprecated/$app..."
        mv "apps/$app" "apps/deprecated/$app"
        
        # Create a README in the deprecated app
        cat > "apps/deprecated/$app/DEPRECATED.md" << EOF
# DEPRECATED: $app

This app has been deprecated and moved to the deprecated folder.

## Reason
This app was a duplicate of other apps in the system, causing:
- Data inconsistency
- Confusion about which models to use
- Maintenance overhead

## Replacement
Use the following instead:
EOF

        # Add replacement info based on app
        case $app in
            "commerce")
                echo "- Use \`stores\` app instead" >> "apps/deprecated/$app/DEPRECATED.md"
                ;;
            "messenger")
                echo "- Use \`messaging\` app with unified PlatformAccount model" >> "apps/deprecated/$app/DEPRECATED.md"
                ;;
            "messaging_v2")
                echo "- Use \`messaging\` app with unified models" >> "apps/deprecated/$app/DEPRECATED.md"
                ;;
            "marketing_v2")
                echo "- Use \`marketing\` app instead" >> "apps/deprecated/$app/DEPRECATED.md"
                ;;
            "core_v2")
                echo "- Use \`core\` app instead" >> "apps/deprecated/$app/DEPRECATED.md"
                ;;
        esac
        
        echo "" >> "apps/deprecated/$app/DEPRECATED.md"
        echo "## Migration Date" >> "apps/deprecated/$app/DEPRECATED.md"
        echo "$(date '+%Y-%m-%d')" >> "apps/deprecated/$app/DEPRECATED.md"
        
        echo "  ✓ Done"
    else
        echo "  ⚠ apps/$app not found, skipping"
    fi
done

echo ""
echo "======================================"
echo "Creating __init__.py for deprecated"
echo "======================================"
touch apps/deprecated/__init__.py

echo ""
echo "======================================"
echo "Summary"
echo "======================================"
echo "Apps moved to apps/deprecated/:"
ls -la apps/deprecated/

echo ""
echo "======================================"
echo "IMPORTANT NEXT STEPS"
echo "======================================"
echo "1. Update INSTALLED_APPS in settings.py to remove deprecated apps"
echo "2. Update any imports in remaining code"
echo "3. Run migrations: python manage.py migrate"
echo "4. Run data migration script: python scripts/migrate_platform_accounts.py"
echo "5. Test thoroughly before deleting deprecated folder"
echo ""
