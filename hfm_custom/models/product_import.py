import pandas as pd


file_path = 'products.xlsx'

xl = pd.ExcelFile(file_path)
sheet_names = xl.sheet_names

categories = sheet_names
parent_products = []
all_products = {}

for sheet_name in sheet_names:
    print("sheet_name ===>>>", sheet_name)
    df = pd.read_excel(file_path, sheet_name=sheet_name)
    
    attributes = []
    for index, row in df.iterrows():
        print(row['Product'], row['Code'])

        
        if row['Product'] not in parent_products:
            parent_products.append(row['Product'])
            product_name = row['Product']
            all_products['product_name'] = {
                'attributes' : attributes,
                'category_name' : sheet_name
            }

        codes = [product['attributes'] for product in all_products]
        if row['Code'] not in codes:
            all_products[row['Product']]['attributes'] += row['Code']


    # for name, values in df.iteritems():
    #     print('{name}: {value}'.format(name=name, value=values[0]))
    #     if name == 'Product':
    #         attributes = []
    #         if name not in parent_products:
    #             parent_products.append(values[0])
    #             product_name = values[0]
    #             all_products.append({
    #                 'product_name' : product_name,
    #                 'attributes' : attributes
    #             })
            
    #         if name == 'Code':
    #             codes = attributes.mapped('code')
    #             if values[0] not in codes:
    #                 all_products[product_name]['attributes'].append({
    #                     'code' : values[0]
    #                 })


print("parent_products ===>>>", parent_products)

print("all_products ===>>>", all_products)