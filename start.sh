#!/bin/bash
tmux new-session -d -s fridge 'python3 control_panel.py'
echo "Fridge-sight started in tmux session 'fridge'"
echo "Attach with: tmux attach -t fridge" 