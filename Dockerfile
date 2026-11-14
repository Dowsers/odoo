# Odoo 19, branche odoowsers : même socle que le serveur d'origine.
#   - Debian 12 (bookworm) et ses paquets python3-*, soit les dépendances du paquet Debian « odoo »
#     et les bibliothèques facultatives présentes sur le serveur (html5lib, olefile, packaging, pygments) ;
#   - client PostgreSQL 18 du dépôt PGDG, requis par « odoo db dump » et « odoo db load » ;
#   - wkhtmltopdf de Debian (0.12.6, Qt non patché, comme le serveur d'origine : les PDF sont identiques,
#     sans en-tête ni pied de page répétés).
# Construction : docker compose build        Documentation : docker/README.md
FROM debian:bookworm-slim

ENV LANG=C.UTF-8 \
    PYTHONUNBUFFERED=1 \
    ODOO_RC=/etc/odoo/odoo.conf

# Utilisateur à identifiants fixes : les volumes gardent le même propriétaire d'une image à l'autre.
RUN groupadd --gid 1000 odoo \
    && useradd --uid 1000 --gid odoo --home-dir /var/lib/odoo --shell /usr/sbin/nologin odoo \
    && install -d -o odoo -g odoo -m 750 /var/lib/odoo /etc/odoo

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates curl; \
    install -d /usr/share/postgresql-common/pgdg; \
    curl -fsSL -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
        https://www.postgresql.org/media/keys/ACCC4CF8.asc; \
    echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" \
        > /etc/apt/sources.list.d/pgdg.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        postgresql-client-18 \
        wkhtmltopdf \
        fonts-dejavu-core fonts-font-awesome fonts-inconsolata fonts-roboto-unhinted gsfonts \
        python3 \
        python3-asn1crypto python3-babel python3-cbor2 python3-chardet python3-cryptography \
        python3-dateutil python3-docutils python3-freezegun python3-geoip2 python3-gevent \
        python3-greenlet python3-idna python3-jinja2 python3-ldap python3-libsass python3-lxml \
        python3-magic python3-markupsafe python3-num2words python3-ofxparse python3-openpyxl \
        python3-openssl python3-passlib python3-pil python3-polib python3-psutil python3-psycopg2 \
        python3-pypdf2 python3-qrcode python3-renderpm python3-reportlab python3-requests \
        python3-rjsmin python3-serial python3-stdnum python3-tz python3-urllib3 python3-usb \
        python3-vobject python3-werkzeug python3-xlrd python3-xlsxwriter python3-xlwt python3-zeep \
        python3-html5lib python3-olefile python3-packaging python3-pygments; \
    rm -rf /var/lib/apt/lists/*

# Sources de la branche (voir .dockerignore), en lecture seule pour l'utilisateur odoo.
COPY . /opt/odoo
RUN set -eux; \
    printf '#!/bin/sh\nexec /opt/odoo/odoo-bin "$@"\n' > /usr/local/bin/odoo; \
    chmod 755 /usr/local/bin/odoo /opt/odoo/odoo-bin /opt/odoo/docker/entrypoint.sh; \
    python3 -m compileall -q -j 0 /opt/odoo/odoo /opt/odoo/addons > /dev/null || true

USER odoo
WORKDIR /var/lib/odoo
VOLUME /var/lib/odoo
EXPOSE 8069

ENTRYPOINT ["/opt/odoo/docker/entrypoint.sh"]
CMD ["odoo", "server"]
