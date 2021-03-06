
# copy package, setup and environment file
cp -r ../kadlu/ .
cp ../setup.py .
cp ../environment.yml .
cp ../docs/sphinx_mer_rtd_theme-0.4.3.dev0.tar.gz .

# build image
docker build --tag=kadlu_v1.0.0 .

# tag image
docker tag kadlu_v1.0.0 meridiancfi/kadlu:v1.0.0

# push image to repository
docker push meridiancfi/kadlu:v1.0.0

# clean
rm -rf kadlu
rm -rf setup.py
rm -rf environment.yml
rm -rf sphinx_mer_rtd_theme-0.4.3.dev0.tar.gz
