$DB_NAME="gpp_plataform"
$DB_USER="postgres"

Write-Host "DROP DATABASE..."
psql -U $DB_USER -c "DROP DATABASE IF EXISTS $DB_NAME;"

Write-Host "CREATE DATABASE..."
psql -U $DB_USER -c "CREATE DATABASE $DB_NAME;"

Write-Host "VALIDANDO BANCO..."
psql -U $DB_USER -lqt | Select-String $DB_NAME

Write-Host "CRIANDO MIGRATIONS..."
python manage.py makemigrations

Write-Host "APLICANDO MIGRATIONS..."
python manage.py migrate

Write-Host "MOSTRANDO MIGRATIONS..."
python manage.py showmigrations

Write-Host "CARREGANDO FIXTURES..."
python manage.py loaddata aplicacoes
python manage.py loaddata initial_data

Write-Host "CRIANDO SUPERUSER..."
python manage.py createsuperuser