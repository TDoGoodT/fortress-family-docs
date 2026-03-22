#!/bin/bash
# Opens the Fortress admin dashboard in the default browser.
# Waits briefly for the app to be ready before opening.

sleep 2

open http://localhost:8000/dashboard 2>/dev/null || \
xdg-open http://localhost:8000/dashboard 2>/dev/null || \
echo "Open http://localhost:8000/dashboard in your browser"
