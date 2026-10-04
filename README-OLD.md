نصب پیش نیازها

```
git clone https://github.com/URT19/Tunnel-Lab.git
cd Tunnel-Lab
chmod +x scripts/install.sh

apt install -y python3-venv python3-full
python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip

```

```
bash scripts/install.sh
python3 main.py
```

