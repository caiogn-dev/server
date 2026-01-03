repo: https://github.com/SEU-USERNAME/pastita-api

# Quick Copy-Paste Commands para EB Deploy

# 1. Configure AWS (one-time)
aws configure
# Cole suas keys do IAM

# 2. Configure EB CLI
eb init -p python-3.11 pastita-api --region sa-east-1

# 3. Deploy
eb create pastita-production --instance-type t3.micro --envvars DEBUG=False,DB_ENGINE=django.db.backends.postgresql,DB_NAME=postgres,DB_USER=postgres,DB_PASSWORD=Caio@2026mano,DB_HOST=db.irrakcwiaubidijzhdok.supabase.co,DB_PORT=5432,MERCADO_PAGO_ACCESS_TOKEN=seu-token,SECRET_KEY=django-insecure-eg*ds206gdc0j_xfm%m%#h#qzo)ycucg@3c=8+=hf#%(@t3gc%

# 4. Abra
eb open

# Done!
