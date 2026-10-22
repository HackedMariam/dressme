
import getpass
import psycopg

password = getpass.getpass("Mot de passe PostgreSQL : ")

try:
    with psycopg.connect(
        host="localhost",
        port=5432,
        dbname="dressme_db",
        user="postgres",
        password=password,
    ) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM catalog_products")
            count = cursor.fetchone()[0]

            print("Connexion PostgreSQL réussie !")
            print(f"Nombre d'articles H&M : {count}")

except psycopg.Error as error:
    print(f"Erreur de connexion : {error}")
