# Run this script by calling wget -qO- https://raw.githubusercontent.com/ForrestFire0/enes100-ml-client/master/install-listener.sh | bash
# RUN IT IN THE ROOT DIRECTORY
sudo rm -r ~/.npm ~/.nvm

wget -qO- https://raw.githubusercontent.com/nvm-sh/nvm/v0.38.0/install.sh | bash
source ~/.bashrc
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh" 
[ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"

nvm install 18

# sudo npm cache clean -f
# sudo npm install -g n
# sudo n stable
# sudo npm install --unsafe-perm=true --allow-root

npm install firebase
npm install node-fetch

mkdir