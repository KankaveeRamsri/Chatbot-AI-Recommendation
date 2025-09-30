import json
from neo4j import GraphDatabase
from tqdm import tqdm

# Setup Neo4j connection
uri = "bolt://localhost:7687"  # Neo4j URI
username = "neo4j"  # Neo4j username
password = "password123"  # Neo4j password

# Initialize Neo4j Driver
driver = GraphDatabase.driver(uri, auth=(username, password))

def save_to_neo4j(product_url, product_name, product_price, product_image_url, product_description):
    session = driver.session()

    try:
        # สร้าง Product node
        session.run("""
            MERGE (p:Product {url: $url})
            SET p.name = $name,
                p.price = $price,
                p.description = $description
            """, url=product_url, name=product_name, price=product_price, description=product_description)

        # สร้าง Image node และเชื่อมกับ Product
        session.run("""
            MATCH (p:Product {url: $url})
            MERGE (i:Image {url: $image_url})
            MERGE (p)-[:HAS_IMAGE]->(i)
            """, url=product_url, image_url=product_image_url)
        
        print(f"Saved: {product_name}")

    except Exception as e:
        print(f"Error saving to Neo4j: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    with open("C:\\Users\\student\\Desktop\\6610110408\\Miniproject-social-3\\products_with_desc.json", "r",encoding="utf-8") as f:
        products = json.load(f)

    COUNT_DEBUG = 0
    for product in tqdm(products, desc="Saving to Neo4j", unit="product"):
        save_to_neo4j(
            product_url=product["link"],
            product_name=product["name"],
            product_price=product["price"],
            product_image_url=product["image"],
            product_description=product["description"]
        )
        COUNT_DEBUG += 1 
    
    print("Success with {} nodes".format(COUNT_DEBUG))

       