# -*- coding: utf-8 -*-
"""item-based recommendation system- comparing all models.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1-7HBY3UxhEnzCJG8jEz67vlabGjYq2hW
"""

import pandas as pd
import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq
from google.colab import drive

# Mount Google Drive
drive.mount('/content/drive')

file_path=f"/content/drive/MyDrive/books_to_kindle_and_books_parquets/books/1_book_after_preprocessing.parquet"

df = pl.read_parquet(file_path)
df_pandas = df.to_pandas()

"""We take only those who are had reviewed at least 50 reviews and no more than 100. On one hand, we do not want users that reviewed 3000 books, with the same review, because this are not legitimic users. On the other hand, we understood that the way recommendation system works is based on data that the user voted, and this is the minimun to make the recommendation system work. Also, some models collapsed while we had other filters such as 10 to 100, and this is just the first file.
 At first we just want to build few pytorch-based recommendation models, and then, once deciding which model we would use, based on its preformance, we will expand the training input, to be not more than just the first file (we have 14 in the drive, making it able to read the whole data in parts).
"""

user_counts = df_pandas['reviewerID'].value_counts()
users_with_50_100_reviews = user_counts[(user_counts >= 50) & (user_counts <= 100)]
num_users_50_100_reviews = len(users_with_50_100_reviews)
print(f"Number of users with 50 -100 records: {num_users_50_100_reviews}")

filtered_users = users_with_50_100_reviews.index.tolist()
df_filtered = df_pandas[df_pandas['reviewerID'].isin(filtered_users)]
print("Filtered DataFrame:")
print(df_filtered)

del df_pandas, df
import gc
gc.collect()

import torch
import torch.nn as nn
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

from torch.utils.data import TensorDataset, DataLoader
import json
from sklearn.metrics import ndcg_score

"""We start with the most simple model and then step by step improve it:"""

train_df, test_df = train_test_split(df_filtered, test_size=0.2)

# Create dictionaries to map user and book IDs to integers
user_to_idx = {user_id: i for i, user_id in enumerate(df_filtered['reviewerID'].unique())}
book_to_idx = {asin: i for i, asin in enumerate(df_filtered['asin'].unique())}

# Convert user and book IDs to integers in the DataFrame
train_df['user_idx'] = train_df['reviewerID'].map(user_to_idx)
train_df['book_idx'] = train_df['asin'].map(book_to_idx)
test_df['user_idx'] = test_df['reviewerID'].map(user_to_idx)
test_df['book_idx'] = test_df['asin'].map(book_to_idx)

"""# First model: simple user/books embedding
The embedding is the part that creates random values which represent the similarity between users and books (with length of n_user or n_books multiplied by n_factors). It could have been achieved also with nn.Parameter(user_factors), and then creating the random values with randn, however, it seems more common in recommendation system to use the embedding in the creation of the model.
"""

class CFModel(nn.Module):
    def __init__(self, df_filtered, n_factors=5):
        super(CFModel, self).__init__()
        n_users = df_filtered['reviewerID'].nunique()
        n_books = df_filtered['asin'].nunique()
        self.user_factors = nn.Embedding(n_users, n_factors)
        self.books_factors = nn.Embedding(n_books, n_factors)

    def forward(self, user_idx, book_idx):
        user_embed = self.user_factors(user_idx)
        book_embed = self.books_factors(book_idx)
        pred_rating = (user_embed * book_embed).sum(dim=1)
        return pred_rating

"""We are storing the models with pickle using built-in pytorch saving syntax, after the training process"""

user_idx_tensor = torch.LongTensor(train_df['user_idx'].values).to(device)
book_idx_tensor = torch.LongTensor(train_df['book_idx'].values).to(device)
ratings_tensor = torch.FloatTensor(train_df['overall'].values).to(device)
train_dataset = TensorDataset(user_idx_tensor, book_idx_tensor, ratings_tensor)
train_loader = DataLoader(train_dataset, batch_size=1024, shuffle=True)
model = CFModel(df_filtered).to(device)

criterion = nn.MSELoss()
optimizer = torch.optim.Adam(model.parameters(), lr=0.01)

num_epochs = 20
for epoch in range(num_epochs):
    model.train()
    total_loss = 0

    for user_idx, book_idx, ratings in train_loader:
        optimizer.zero_grad()
        pred_ratings = model(user_idx, book_idx)
        loss = criterion(pred_ratings, ratings)
        loss.backward()
        optimizer.step()
        total_loss += loss.item()

    avg_loss = total_loss / len(train_loader)
    print(f'Epoch {epoch+1}/{num_epochs}, Average Loss: {avg_loss:.4f}')

torch.save(model.state_dict(), '/content/drive/MyDrive/models/first_cf_model.pth')

"""
At the begining we started with evaluation of the RMSE, however, after a while, we decided to add NDCG since it prioritizes the ranking of recommendations over the absolute accuracy of predicted ratings, which is crucial in scenarios like movie or product suggestions where a precise rating (such as 4.2 vs. 4.5) is less critical than ensuring the most appreciated items top the list. NDCG also emphasizes the relevance of items at the start of the recommendation list, where user engagement is highest, thus enhancing user satisfaction as users typically interact more with these initial recommendations. Additionally, unlike RMSE, NDCG can be applied to data without explicit numerical ratings, handling both binary and graded relevance, making it versatile across various recommendation system types. This focus on user experience aligns closely with business objectives, such as increasing user engagement, satisfaction, and retention, by ensuring the quality of the rankings and prioritizing the most impactful part of the list.

Evantually we ended up with many more metrics so we can evaluate the model performances based on multiple values, hearing the instructor opinion, and also maybe gaining a deeper perspective."""

from sklearn.metrics import mean_absolute_error, precision_recall_fscore_support, ndcg_score, label_ranking_average_precision_score
import numpy as np

def calculate_mrr(true_ratings, pred_ratings):
    order = np.argsort(-pred_ratings)  # Get indices of sorted ratings in descending order
    true_order = np.argsort(-true_ratings)
    rank = np.empty_like(order)
    true_rank = np.empty_like(true_order)
    rank[order] = np.arange(len(pred_ratings))
    true_rank[true_order] = np.arange(len(true_ratings))

    # Determine ranks of the true relevant items
    relevance_ranks = true_rank[order]
    mrr = 0.0
    for r in relevance_ranks:
        mrr += 1.0 / (r + 1)
    mrr /= len(relevance_ranks)
    return mrr

from sklearn.metrics import label_ranking_average_precision_score

def calculate_map(true_ratings, pred_ratings):
    # Create a sorted index based on true ratings, high to low
    ideal_rank = np.argsort(-true_ratings)
    # Create a sorted index based on predicted ratings, high to low
    predicted_rank = np.argsort(-pred_ratings)

    # Generate ideal and predicted rank lists
    ideal_rank_list = [np.where(ideal_rank == i)[0][0] for i in range(len(true_ratings))]
    predicted_rank_list = [np.where(predicted_rank == i)[0][0] for i in range(len(true_ratings))]

    # Convert ranks to binary relevance: top X% as relevant
    cutoff_percent = 20
    cutoff = len(true_ratings) * cutoff_percent // 100
    ideal_relevance = [1 if x < cutoff else 0 for x in ideal_rank_list]
    predicted_relevance = [1 if x < cutoff else 0 for x in predicted_rank_list]

    return label_ranking_average_precision_score([ideal_relevance], [predicted_relevance])

user_idx_tensor_test = torch.LongTensor(test_df['user_idx'].values).to(device)
book_idx_tensor_test = torch.LongTensor(test_df['book_idx'].values).to(device)
model.eval()
pred_ratings_test = model(user_idx_tensor_test, book_idx_tensor_test).detach().cpu().numpy()
true_ratings = test_df['overall'].values

ndcg = ndcg_score([true_ratings], [pred_ratings_test])

mae = mean_absolute_error(true_ratings, pred_ratings_test)

mrr = calculate_mrr(true_ratings, pred_ratings_test)

precision, recall, f1, _ = precision_recall_fscore_support(true_ratings, pred_ratings_test.round(), average='macro')

rmse = np.sqrt(mean_squared_error(true_ratings, pred_ratings_test, squared=False))

map_score = calculate_map(true_ratings, pred_ratings_test)
print(f"Metrics:\nNDCG: {ndcg:.4f}\nMAE: {mae:.4f}\nMRR: {mrr:.4f}\nPrecision: {precision:.4f}\nRecall: {recall:.4f}\nF1-score: {f1:.4f}\nRMSE: {rmse:.4f}\nMAP: {map_score:.4f}")

"""We decided to store that metrics for later use, so we would be able to compare the models without retraining them."""

import json

def save_performance_data(model_name, mae, rmse, precision, recall, f1, ndcg, mrr, map_score):
    performance_data = {
        'model_name': model_name, 'mae': mae, 'rmse': rmse,
        'precision': precision, 'recall': recall, 'f1': f1,
        'ndcg': ndcg, 'mrr': mrr, 'map': map_score
    }
    file_path = '/content/drive/MyDrive/models/model_performance.json'

    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
    except FileNotFoundError:
        data = []

    data.append(performance_data)

    # Write back to JSON
    with open(file_path, 'w') as f:
        json.dump(data, f, indent=4)

save_performance_data('first_cf_model', mae, rmse, precision, recall, f1, ndcg, mrr, map_score)

"""### Adding bias
This is done since there are users who rate more positive or negative than others, and there are some books that are plain better or worse than others. We will create number for each user that we can add to our socres and ditto for each book, to handle that.
"""

n_factors = 5
n_users = df_filtered['reviewerID'].nunique()
n_books = df_filtered['asin'].nunique()

"""We read that for a 1-5 rating range (and 0 as "not rated") it is recommended to define y_range as 0-5.5 because it turns out that it has better accuracy."""

class CollaborativeFilteringModel(nn.Module):
    def __init__(self, n_users, n_books, n_factors=5, y_range=(0, 5.5)):
        super(CollaborativeFilteringModel, self).__init__()
        self.user_factors = nn.Embedding(n_users, n_factors)
        self.user_bias = nn.Embedding(n_users, 1)
        self.book_factors = nn.Embedding(n_books, n_factors)
        self.book_bias = nn.Embedding(n_books, 1)
        self.y_range = y_range

    def forward(self, user_idx, book_idx):
        user_embed = self.user_factors(user_idx)
        book_embed = self.book_factors(book_idx)
        user_bias = self.user_bias(user_idx)
        book_bias = self.book_bias(book_idx)
        res = (user_embed * book_embed).sum(dim=1, keepdim=True)
        res += user_bias + book_bias
        predicted_rating = torch.sigmoid(res)
        return predicted_rating * (self.y_range[1] - self.y_range[0]) + self.y_range[0]

model = CollaborativeFilteringModel(n_users,n_books, n_factors).to(device)

user_idx_tensor = torch.LongTensor(train_df['user_idx'].values).to(device)
book_idx_tensor = torch.LongTensor(train_df['book_idx'].values).to(device)
ratings_tensor = torch.FloatTensor(train_df['overall'].values).to(device)

train_dataset = TensorDataset(user_idx_tensor, book_idx_tensor, ratings_tensor)
train_loader = DataLoader(train_dataset, batch_size=1024, shuffle=True)

criterion = nn.MSELoss()
optimizer = torch.optim.Adam(model.parameters(), lr=0.01)

num_epochs = 20
for epoch in range(num_epochs):
    model.train()
    total_loss = 0

    for user_idx, book_idx, ratings in train_loader:
        optimizer.zero_grad()
        pred_ratings = model(user_idx, book_idx)
        loss = criterion(pred_ratings, ratings)
        loss.backward()
        optimizer.step()
        total_loss += loss.item()

    avg_loss = total_loss / len(train_loader)
    print(f'Epoch {epoch+1}/{num_epochs}, Average Loss: {avg_loss:.4f}')



torch.save(model.state_dict(), '/content/drive/MyDrive/models/fc_with_bias_model.pth')

user_idx_tensor_test = torch.LongTensor(test_df['user_idx'].values).to(device)
book_idx_tensor_test = torch.LongTensor(test_df['book_idx'].values).to(device)
model.eval()
pred_ratings_test = model(user_idx_tensor_test, book_idx_tensor_test).detach().cpu().numpy()
true_ratings = test_df['overall'].values
true_ratings, pred_ratings_test =  true_ratings.reshape(-1), pred_ratings_test.reshape(-1)

ndcg = ndcg_score([true_ratings], [pred_ratings_test])

mae = mean_absolute_error(true_ratings, pred_ratings_test)

mrr = calculate_mrr(true_ratings, pred_ratings_test)

precision, recall, f1, _ = precision_recall_fscore_support(true_ratings, pred_ratings_test.round(), average='macro')

rmse = np.sqrt(mean_squared_error(true_ratings, pred_ratings_test, squared=False))

map_score = calculate_map(true_ratings, pred_ratings_test)
print(f"Metrics:\nNDCG: {ndcg:.4f}\nMAE: {mae:.4f}\nMRR: {mrr:.4f}\nPrecision: {precision:.4f}\nRecall: {recall:.4f}\nF1-score: {f1:.4f}\nRMSE: {rmse:.4f}\nMAP: {map_score:.4f}")
save_performance_data('fc_with_bias_model', mae, rmse, precision, recall, f1, ndcg, mrr, map_score)

"""### Regularization:
In order to prevent overfitting, we would now create another model that uses regularization
"""

model_with_regularization = CollaborativeFilteringModel(n_users,n_books, n_factors).to(device)

criterion = nn.MSELoss()
optimizer = torch.optim.Adam(model_with_regularization.parameters(), lr=0.01, weight_decay=0.01)
# Added L2 regularization with weight_decay

user_idx_tensor = torch.LongTensor(train_df['user_idx'].values).to(device)
book_idx_tensor = torch.LongTensor(train_df['book_idx'].values).to(device)
ratings_tensor = torch.FloatTensor(train_df['overall'].values).to(device)

train_dataset = TensorDataset(user_idx_tensor, book_idx_tensor, ratings_tensor)
train_loader = DataLoader(train_dataset, batch_size=1024, shuffle=True)

num_epochs = 20
for epoch in range(num_epochs):
    model_with_regularization.train()
    total_loss = 0

    for user_idx, book_idx, ratings in train_loader:
        optimizer.zero_grad()
        pred_ratings = model_with_regularization(user_idx, book_idx)
        loss = criterion(pred_ratings, ratings)
        loss.backward()
        optimizer.step()
        total_loss += loss.item()

    avg_loss = total_loss / len(train_loader)
    print(f'Epoch {epoch+1}/{num_epochs}, Average Loss: {avg_loss:.4f}')

torch.save(model_with_regularization.state_dict(), '/content/drive/MyDrive/models/fc_with_bias_and_regularization_model.pth')

user_idx_tensor_test = torch.LongTensor(test_df['user_idx'].values).to(device)
book_idx_tensor_test = torch.LongTensor(test_df['book_idx'].values).to(device)
model.eval()
pred_ratings_test = model(user_idx_tensor_test, book_idx_tensor_test).detach().cpu().numpy()
true_ratings = test_df['overall'].values
true_ratings, pred_ratings_test =  true_ratings.reshape(-1), pred_ratings_test.reshape(-1)

ndcg = ndcg_score([true_ratings], [pred_ratings_test])

mae = mean_absolute_error(true_ratings, pred_ratings_test)

mrr = calculate_mrr(true_ratings, pred_ratings_test)

precision, recall, f1, _ = precision_recall_fscore_support(true_ratings, pred_ratings_test.round(), average='macro')

rmse = np.sqrt(mean_squared_error(true_ratings, pred_ratings_test, squared=False))

map_score = calculate_map(true_ratings, pred_ratings_test)
print(f"Metrics:\nNDCG: {ndcg:.4f}\nMAE: {mae:.4f}\nMRR: {mrr:.4f}\nPrecision: {precision:.4f}\nRecall: {recall:.4f}\nF1-score: {f1:.4f}\nRMSE: {rmse:.4f}\nMAP: {map_score:.4f}")
save_performance_data('fc_with_bias_and_regularization_model', mae, rmse, precision, recall, f1, ndcg, mrr, map_score)

"""Let's see if we can get recommendation based on our models so far (future work will include to change the recommended books numbers to actually boooks):"""

# Generate top recommendations for each user
all_users = train_df['user_idx'].unique()
all_books = train_df['book_idx'].unique()

recommendations = []

with torch.no_grad():
    for user in all_users:
        user_idx_tensor = torch.LongTensor([user] * len(all_books))
        book_idx_tensor = torch.LongTensor(all_books)
        pred_ratings = model(user_idx_tensor, book_idx_tensor).squeeze()
        top_books_idx = torch.argsort(pred_ratings, descending=True)[:10]  # Top 10 recommendations
        top_books = all_books[top_books_idx]
        recommendations.append((user, top_books))

# Print top recommendations for each user
for user, recs in recommendations:
    print(f"Top recommendations for user {user}: {recs}")



"""We want to use as much data as we can and compare all the models we can create. Another idea is to use the 'category' value, that can be taken form the "metadata" database, that maps every asin to its category."""

file_path=f"/content/drive/MyDrive/meta-books-parquet/meta_books_chunk_1.parquet"

import polars as pl
import pandas as pd

df_meta = pl.read_parquet(file_path)
df_meta_pandas = df_meta.to_pandas()

dataframes = []


for i in range(1, 148):

    file_path = f"/content/drive/MyDrive/meta-books-parquet/meta-books-csv-chunk_{i}.parquet"

    df_meta = pl.read_parquet(file_path)

    df_meta_pandas = df_meta.to_pandas()

    dataframes.append(df_meta_pandas)

combined_df = pd.concat(dataframes, ignore_index=True)

combined_df['category'] = combined_df['category'].astype(str)

counting_genres=combined_df['category'].value_counts()

counting_genres.to_csv("counting_genres.csv")

counting_genres

df = counting_genres.reset_index()
df.columns = ['category', 'count']
df.head()

import ast
def string_to_list(category_string):
    return ast.literal_eval(category_string)

import re


# Function to extract the desired category based on the input in the metadat file
def extract_category(categories):
    if not categories:
        return "unknown"  # we have edge case of "[]" in the categories, as you can see above
    if len(categories) == 1:
        return categories[0]
    else:
      second_item = categories[1]
      third_item = categories[2] if len(categories) > 2 else None

    # Check for specific categories
    # if the second category is "New, Used & Rental Textbooks" we move to the third item
    if re.match(r'New, Used (&amp;|&) Rental Textbooks', second_item):
        if third_item:
            return third_item
        # this case is when there are only two categories (['Books', 'New, Used &amp; Rental Textbooks'] or ['Books', 'New, Used & Rental Textbooks'])
        return "unknown"
    else:
        # Return the second category, with "&amp" replaced to "&"
        return re.sub(r'&amp;', '&', second_item)
df['category_list'] = df['category'].apply(string_to_list)

# Apply the function to the category column
df['extracted_category'] = df['category_list'].apply(extract_category)

print(df[['extracted_category']])

df['extracted_category'] = df['extracted_category'].astype(str)
grouped_df = df.groupby('extracted_category')['count'].sum().reset_index()

print(grouped_df)

"""Now we combine categories based on common knowledge, and what we think that should be the same category"""

replacement_dict = {
    'Business & Finance': 'Business & Money',
    'Business &amp; Finance': 'Business & Money',
    'Communication &amp; Journalism': 'Communication & Journalism',
    'Computers & Technology': 'Computer Science',
    'Education': 'Education & Teaching',
    'Medicine & Health Sciences': 'Medical Books',
    'Medicine &amp; Health Sciences': 'Medical Books',
    'Science & Mathematics': 'Science & Math',
    'Science &amp; Mathematics': 'Science & Math',
    'Social Sciences': 'Politics & Social Sciences',
    'Test Prep & Study Guides': 'Test Preparation',
    'Test Prep &amp; Study Guides': 'Test Preparation'
}


df['extracted_category'] = df['extracted_category'].replace(replacement_dict)

grouped_df = df.groupby('extracted_category')['count'].sum().reset_index()
print(grouped_df)

""" Merging the extracted categories (df) after all preprocessing, with the relevant asins from the combnined_df that contains all the metadata categories"""

combined_df = combined_df[["category", "asin"]]

combined_df.head()

result_df = combined_df.merge(df, on='category', how='left')

result_df= result_df[["asin", "extracted_category"]]

print(result_df)

result_df.to_parquet("asin_to_category.parquet")

"""Now we combine the first file  we have now in the memory with the asin_to_category, to get the reviews, with their categories"""

asin_file=f"/content/drive/MyDrive/asin_to_category.parquet"

asin_to_category = pd.read_parquet(asin_file)

"""The result of next line is the reviews, with generes extracted from the metadata file:"""

result_df = df_filtered.merge(asin_to_category, on='asin', how='left')

result_df['extracted_category'].nunique()

result_df['extracted_category'].unique()

train_df, test_df = train_test_split(result_df, test_size=0.2)

user_to_idx = {user_id: i for i, user_id in enumerate(result_df['reviewerID'].unique())}
book_to_idx = {asin: i for i, asin in enumerate(result_df['asin'].unique())}

category_to_idx = {}
categories = result_df['extracted_category'].unique()
categories_series = pd.Series(categories)

# Drop "unknown" category
categories = categories_series[categories_series != "unknown"].to_numpy()

for i, category in enumerate(categories):
        category_to_idx[category] = i

# Add the special index for unknown categories
category_to_idx['unknown'] = i+1

train_df['user_idx'] = train_df['reviewerID'].map(user_to_idx)
train_df['book_idx'] = train_df['asin'].map(book_to_idx)
train_df['category_idx'] = train_df['extracted_category'].map(category_to_idx)
test_df['user_idx'] = test_df['reviewerID'].map(user_to_idx)
test_df['book_idx'] = test_df['asin'].map(book_to_idx)
test_df['category_idx'] = test_df['extracted_category'].map(category_to_idx)

from torch.utils.data import TensorDataset, DataLoader

# Create TensorDatasets and DataLoaders
train_dataset = TensorDataset(
    torch.LongTensor(train_df['user_idx'].values),
    torch.LongTensor(train_df['book_idx'].values),
    torch.LongTensor(train_df['category_idx'].values),
    torch.FloatTensor(train_df['overall'].values)
)
train_loader = DataLoader(train_dataset, batch_size=1024, shuffle=True)

test_dataset = TensorDataset(
    torch.LongTensor(test_df['user_idx'].values),
    torch.LongTensor(test_df['book_idx'].values),
    torch.LongTensor(test_df['category_idx'].values),
    torch.FloatTensor(test_df['overall'].values)
)
test_loader = DataLoader(test_dataset, batch_size=1024, shuffle=False)

import torch
import torch.nn as nn
from sklearn.metrics import mean_squared_error

class CollaborativeFilteringModel(nn.Module):
    def __init__(self, result_df, n_factors=5, y_range=(0, 5.5)):
        super(CollaborativeFilteringModel, self).__init__()
        n_users, n_books, n_categories = result_df['reviewerID'].nunique(), result_df['asin'].nunique(), result_df['extracted_category'].nunique()
        self.n_categories = n_categories
        self.user_factors = nn.Embedding(n_users, n_factors)
        self.user_bias = nn.Embedding(n_users, 1)
        self.book_factors = nn.Embedding(n_books, n_factors)
        self.book_bias = nn.Embedding(n_books, 1)
        self.category_factors = nn.Embedding(n_categories, n_factors)
        self.y_range = y_range

    def forward(self, user_idx, book_idx, category_idx):
        user_embed = self.user_factors(user_idx)
        book_embed = self.book_factors(book_idx)
        # Handle unknown categories by using a neutral vector
        category_embed = self.category_factors(category_idx)
        unknown_category_mask = category_idx == (self.n_categories - 1)
        category_embed = torch.where(unknown_category_mask.unsqueeze(1), torch.zeros_like(category_embed), category_embed)


        user_bias = self.user_bias(user_idx)
        book_bias = self.book_bias(book_idx)

        res = (user_embed * book_embed * category_embed).sum(dim=1, keepdim=True)
        res += user_bias + book_bias
        predicted_rating = torch.sigmoid(res)
        return predicted_rating * (self.y_range[1] - self.y_range[0]) + self.y_range[0]

n_categories = 33
model = CollaborativeFilteringModel(result_df).to(device)
criterion = nn.MSELoss()
optimizer = torch.optim.Adam(model.parameters(), lr=0.01, weight_decay=0.01)

user_idx_tensor = torch.LongTensor(train_df['user_idx'].values).to(device)
book_idx_tensor = torch.LongTensor(train_df['book_idx'].values).to(device)
ratings_tensor = torch.FloatTensor(train_df['overall'].values).to(device)
category_idx_tensor = torch.LongTensor(train_df['category_idx'].values).to(device)

train_dataset = TensorDataset(user_idx_tensor, book_idx_tensor, ratings_tensor, category_idx_tensor)
train_loader = DataLoader(train_dataset, batch_size=1024, shuffle=True)

num_epochs = 20
for epoch in range(num_epochs):
    model.train()
    total_loss = 0

    for user_idx_batch, book_idx_batch, ratings_batch, category_idx_batch in train_loader:
        optimizer.zero_grad()
        pred_ratings = model(user_idx_batch, book_idx_batch, category_idx_batch).squeeze()
        loss = criterion(pred_ratings, ratings_batch)
        loss.backward()
        optimizer.step()
        total_loss += loss.item()

    avg_loss = total_loss / len(train_loader)
    print(f'Epoch {epoch+1}/{num_epochs}, Average Loss: {avg_loss}')

torch.save(model.state_dict(), '/content/drive/MyDrive/models/fc_with_category.pth')

user_idx_tensor_test = torch.LongTensor(test_df['user_idx'].values).to(device)

book_idx_tensor_test = torch.LongTensor(test_df['book_idx'].values).to(device)
category_idx_tensor = torch.LongTensor(test_df['category_idx'].values).to(device)

model.eval()
with torch.no_grad():
    pred_ratings_test = model(user_idx_tensor_test, book_idx_tensor_test, category_idx_tensor).squeeze().cpu().numpy()
true_ratings = test_df['overall'].values
true_ratings, pred_ratings_test =  true_ratings.reshape(-1), pred_ratings_test.reshape(-1)

ndcg = ndcg_score([true_ratings], [pred_ratings_test])

mae = mean_absolute_error(true_ratings, pred_ratings_test)

mrr = calculate_mrr(true_ratings, pred_ratings_test)

precision, recall, f1, _ = precision_recall_fscore_support(true_ratings, pred_ratings_test.round(), average='macro')

rmse = np.sqrt(mean_squared_error(true_ratings, pred_ratings_test, squared=False))

map_score = calculate_map(true_ratings, pred_ratings_test)
print(f"Metrics:\nNDCG: {ndcg:.4f}\nMAE: {mae:.4f}\nMRR: {mrr:.4f}\nPrecision: {precision:.4f}\nRecall: {recall:.4f}\nF1-score: {f1:.4f}\nRMSE: {rmse:.4f}\nMAP: {map_score:.4f}")
save_performance_data('fc_with_category', mae, rmse, precision, recall, f1, ndcg, mrr, map_score)

"""# Sentiment

Next we want to generate a senitment based on our features "reviewText", and "summary", working with already made models
"""

!pip install transformers

result_df

"""We are using distilbert-base-uncased-finetuned-sst-2-english model which it's performance considered pretty good, and for each text returns "NEGATIVE", or "POSITIVE" and a number between 0.5 and 1, representing how much positive or negative the sentiment is."""

from transformers import pipeline, DistilBertTokenizer

sentiment_analysis = pipeline('sentiment-analysis', model="distilbert-base-uncased-finetuned-sst-2-english")

# Initialize the tokenizer
tokenizer = DistilBertTokenizer.from_pretrained("distilbert-base-uncased-finetuned-sst-2-english")

"""In the following code, we first created a code that uses summary if exists, and only if not we would get the sentiment of the full review text. We saw by manually examiming the created sentiment that the sentiment of the summary usually generate poor results, like a row of 5 star rating, that had a summary "try it" and got 0.6 in the positive sentiment (range is 0.5-1, which means it wasn't adding inforamtion for our model). Then after seeing that sometimes a review of 3, might have very criticizing reveiew text, and some of the 3-stars records do have pretty good reviews, so we decided that we want to run the sentiment for the full review text. However, due to the limitation of 512 tokens maximus passed to sentiment models, and due to the amount of data that needs to be calculated the sentiment of and lack of resources (time and memory this case), we would take only first 512 tokens. For some reason, even that is too much for the sentiment model, so we decreased it even less, so now the model is using only first 510 tokens from every reveiw.

As it is quite heavy to run, we will show some statistics based on only the first 1000. Later we created sentiment (in parts) of all the records and it will be uploaded to the model.
"""

def get_sentiment_score(row):
    text = row['reviewText']
    if pd.isna(text):
        return None  # Return None if  reviewText is missing

    # Tokenize the text and truncate to the first 510 tokens
    tokens = tokenizer.encode(text, add_special_tokens=True, max_length=510, truncation=True)

    # Convert tokens back to text string if necessary
    truncated_text = tokenizer.decode(tokens)

    # Perform sentiment analysis
    result = sentiment_analysis(truncated_text)[0]
    if result['label'] == "NEGATIVE":
        score = -result['score']
    else:
        score = result['score']
    return (score, result['label'])  # Return tuple

result_df_head = result_df.head(1000)
result_df_head['sentiment_result'] = result_df_head.apply(get_sentiment_score, axis=1)

result_df_head[['sentiment_score', 'sentiment_label']] = pd.DataFrame(result_df_head['sentiment_result'].tolist(), index=result_df_head.index)
print(result_df_head.head())

result_df_head["sentiment_label" ].value_counts()

result_df_head["sentiment_score" ].describe()

import matplotlib.pyplot as plt
# Creating a histogram of the sentiment scores
plt.hist(result_df_head["sentiment_score"], bins=20, color='blue', edgecolor='black')
plt.title('Histogram of Sentiment Scores')
plt.xlabel('Sentiment Score')
plt.ylabel('Frequency')
plt.grid(True)
plt.show()

"""As we can see from our sample data, most of the data that is extracted from the review text is either very close to 1 and -1, meaning very positive or negative, and there is a minority that is between 0.5-0.9 and -0.5 and -0.9.
The reason why there is no data between -0.5 and 0.5 is that the sentiment originally is values from 0.5-1 for either positive or negative, meaning, 0.4 of positive is equal to 0.6 negative, so the model is trained to decide either negative or positive. Since of this distribution of the data, we would like to perform discritization, so eventually there would be only 4 values for the sentiment: values that are positive above 0.9 would be classified as "loved", where below that would be "liked". for negative sentiment, we would define values above 0.9 as "hated", where below would be "disliked".
"""

average_sentiment = result_df_head.loc[(result_df_head['sentiment_score'] > 0.5) & (result_df_head['sentiment_score'] < 0.9)]
average_sentiment.head(20)

def get_sentiment_category(text):
    if pd.isna(text):
        return None

    tokens = tokenizer.encode(text, add_special_tokens=True, max_length=510, truncation=True)

    truncated_text = tokenizer.decode(tokens)

    result = sentiment_analysis(truncated_text)[0]
    score = result['score']
    sentiment = result['label']

    if sentiment == "POSITIVE":
        if score > 0.9:
            category = 3 # "Loved"
        else:
            category = 2 # "Liked"
    elif sentiment == "NEGATIVE":
        if score > 0.9:
            category = 0 # "Hated"
        else:
          category = 1 # "Disliked"

    return category  # Return the category
result_df['sentiment_category'] = result_df["reviewText"].apply(get_sentiment_category)
result_df = result_df.drop(columns=["verified", "reviewText", "summary"])
result_df.to_parquet('/content/drive/MyDrive/books_to_kindle_and_books_parquets/booksכככ/books_1_with_sentiment.parquet')
result_df.head()

"""We kept the summary and review text for a long time, however, we can't extract really important data from the review text rather the sentiment, so it seems like the right time to drop them. In addition, we first thought that we would use the feature "verified: True/False" but this also seems meaningless, so we would drop that as well.

From here on we would use the sentiment in our model
"""

sentiment_path=f"/content/drive/MyDrive/books_to_kindle_and_books_parquets/books/combined_books_1_with_sentiment.parquet"

result_df = pd.read_parquet(sentiment_path)

result_df.head()

class SentimentModel(nn.Module):
    def __init__(self, n_users, n_books, n_categories, n_sentiments=4, n_factors=5, y_range=(0, 5.5)):
        super(SentimentModel, self).__init__()
        self.n_categories = n_categories
        self.user_factors = nn.Embedding(n_users, n_factors)
        self.user_bias = nn.Embedding(n_users, 1)
        self.book_factors = nn.Embedding(n_books, n_factors)
        self.book_bias = nn.Embedding(n_books, 1)
        self.category_factors = nn.Embedding(n_categories, n_factors)
        self.sentiment_factors = nn.Embedding(n_sentiments, n_factors)
        self.y_range = y_range

    def forward(self, user_idx, book_idx, category_idx, sentiment_idx):
        user_embed = self.user_factors(user_idx)
        book_embed = self.book_factors(book_idx)
        category_embed = self.category_factors(category_idx)
        sentiment_embed = self.sentiment_factors(sentiment_idx)

        unknown_category_mask = category_idx == (self.n_categories - 1)
        category_embed = torch.where(unknown_category_mask.unsqueeze(1), torch.zeros_like(category_embed), category_embed)

        user_bias = self.user_bias(user_idx)
        book_bias = self.book_bias(book_idx)

        res = (user_embed * book_embed * category_embed * sentiment_embed).sum(dim=1, keepdim=True)
        res += user_bias + book_bias
        predicted_rating = torch.sigmoid(res)
        return predicted_rating * (self.y_range[1] - self.y_range[0]) + self.y_range[0]

train_df, test_df = train_test_split(result_df, test_size=0.2)

# Create dictionaries to map user and book IDs to integers
user_to_idx = {user_id: i for i, user_id in enumerate(result_df['reviewerID'].unique())}
book_to_idx = {asin: i for i, asin in enumerate(result_df['asin'].unique())}
category_to_idx = {}
categories = result_df['extracted_category'].unique()
categories_series = pd.Series(categories)

# Drop "unknown" category
categories = categories_series[categories_series != "unknown"].to_numpy()

for i, category in enumerate(categories):
    category_to_idx[category] = i

# Add the special index for unknown categories
category_to_idx['unknown'] = i + 1

train_df['user_idx'] = train_df['reviewerID'].map(user_to_idx)
train_df['book_idx'] = train_df['asin'].map(book_to_idx)
train_df['category_idx'] = train_df['extracted_category'].map(category_to_idx)
test_df['user_idx'] = test_df['reviewerID'].map(user_to_idx)
test_df['book_idx'] = test_df['asin'].map(book_to_idx)
test_df['category_idx'] = test_df['extracted_category'].map(category_to_idx)

train_dataset = TensorDataset(
    torch.LongTensor(train_df['user_idx'].values),
    torch.LongTensor(train_df['book_idx'].values),
    torch.LongTensor(train_df['category_idx'].values),
    torch.LongTensor(train_df['sentiment_category'].values),
    torch.FloatTensor(train_df['overall'].values)
)
train_loader = DataLoader(train_dataset, batch_size=1024, shuffle=True)

test_dataset = TensorDataset(
    torch.LongTensor(test_df['user_idx'].values),
    torch.LongTensor(test_df['book_idx'].values),
    torch.LongTensor(test_df['category_idx'].values),
    torch.LongTensor(test_df['sentiment_category'].values),
    torch.FloatTensor(test_df['overall'].values)
)
test_loader = DataLoader(test_dataset, batch_size=1024, shuffle=False)

n_users = result_df['reviewerID'].nunique()
n_books = result_df['asin'].nunique()
n_categories = result_df['extracted_category'].nunique()
n_sentiments = 4

model = SentimentModel(n_users,n_books,n_categories,n_sentiments).to(device)
criterion = nn.MSELoss()
optimizer = torch.optim.Adam(model.parameters(), lr=0.01, weight_decay=0.01)

num_epochs = 20
for epoch in range(num_epochs):
    model.train()
    total_loss = 0

    for user_idx_batch, book_idx_batch, category_idx_batch, sentiment_idx_batch, ratings_batch in train_loader:
        optimizer.zero_grad()
        pred_ratings = model(user_idx_batch, book_idx_batch, category_idx_batch, sentiment_idx_batch).squeeze()
        loss = criterion(pred_ratings, ratings_batch)
        loss.backward()
        optimizer.step()
        total_loss += loss.item()

    avg_loss = total_loss / len(train_loader)
    print(f'Epoch {epoch+1}/{num_epochs}, Average Loss: {avg_loss}')

# Save model parameters
torch.save(model.state_dict(), '/content/drive/MyDrive/models/cf_with_sentiment.pth')

user_idx_tensor_test = torch.LongTensor(test_df['user_idx'].values).to(device)
book_idx_tensor_test = torch.LongTensor(test_df['book_idx'].values).to(device)
category_idx_tensor_test = torch.LongTensor(test_df['category_idx'].values).to(device)
sentiment_idx_tensor_test = torch.LongTensor(test_df['sentiment_category'].values).to(device)

model.eval()
with torch.no_grad():
    pred_ratings_test = model(user_idx_tensor_test, book_idx_tensor_test, category_idx_tensor_test, sentiment_idx_tensor_test).squeeze().cpu().numpy()

true_ratings = test_df['overall'].values
true_ratings, pred_ratings_test = true_ratings.reshape(-1), pred_ratings_test.reshape(-1)

ndcg = ndcg_score([true_ratings], [pred_ratings_test])
mae = mean_absolute_error(true_ratings, pred_ratings_test)
mrr = calculate_mrr(true_ratings, pred_ratings_test)
precision, recall, f1, _ = precision_recall_fscore_support(true_ratings, pred_ratings_test.round(), average='macro')
rmse = np.sqrt(mean_squared_error(true_ratings, pred_ratings_test))
map_score = calculate_map(true_ratings, pred_ratings_test)

print(f"Metrics:\nNDCG: {ndcg:.4f}\nMAE: {mae:.4f}\nMRR: {mrr:.4f}\nPrecision: {precision:.4f}\nRecall: {recall:.4f}\nF1-score: {f1:.4f}\nRMSE: {rmse:.4f}\nMAP: {map_score:.4f}")
save_performance_data('cf_with_sentiment', mae, rmse, precision, recall, f1, ndcg, mrr, map_score)

"""# Thoughts going forward

We see that some models work better than others. Especially when adding bias. The next stpes will be comparing all of the models, choosting top 2 or top 3, then conducting error anaylisys and going forward we will choose only one to try and perfect it as much as possible.
"""