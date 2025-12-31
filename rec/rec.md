# record terminal

## install tools

```bash
sudo apt install asciinema
wget https://github.com/asciinema/agg/releases/latest/download/agg-x86_64-unknown-linux-gnu -O agg
chmod +x agg
sudo mv agg /usr/local/bin/
```

## record terminal and transform to gif
```bash
export USER="wlanboy"
export LOGNAME="wlanboy"
export PS1=" \W > "
asciinema rec -c "PS1='> ' bash --norc" vm_setup.cast
uv run generator.py

agg --theme dracula vm_setup.cast vm_setup.gif
```

