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
asciinema rec -c 'PS1="\W \$ " bash' vm_setup.cast
agg --theme dracula vm_setup.cast vm_setup.gif
```

