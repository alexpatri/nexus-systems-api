package database

import (
	"context"
	"time"

	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/bson/primitive"
	"go.mongodb.org/mongo-driver/mongo"
	"go.mongodb.org/mongo-driver/mongo/options"
)

type DataBase struct {
	dataBase *mongo.Database
	client   *mongo.Client
}

func NewMongoDB(mongoURI, dbName string) (*DataBase, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	client, err := mongo.Connect(ctx, options.Client().ApplyURI(mongoURI))
	if err != nil {
		return nil, err
	}

	return &DataBase{
		dataBase: client.Database(dbName),
		client:   client,
	}, nil
}

func ConvertMapToBson(filterMap map[string]string) bson.M {
	filter := bson.M{}
	for key, value := range filterMap {
		filter[key] = value
	}
	return filter
}

func IsErrNoDocuments(err error) bool {
	return err == mongo.ErrNoDocuments
}

func (mongo *DataBase) InsertOne(collectionName string, val interface{}) (*mongo.InsertOneResult, error) {
	data, err := bson.Marshal(val)
	if err != nil {
		return nil, err
	}

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	collection := mongo.dataBase.Collection(collectionName)

	return collection.InsertOne(ctx, data)
}

func (mongo *DataBase) FindOne(collectionName string, filter interface{}, result interface{}) error {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	collection := mongo.dataBase.Collection(collectionName)

	return collection.FindOne(ctx, filter).Decode(result)
}

func (mongo *DataBase) FindOneByID(collectionName string, id string, result interface{}) error {
	objID, err := primitive.ObjectIDFromHex(id)
	if err != nil {
		return err
	}

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	collection := mongo.dataBase.Collection(collectionName)

	return collection.FindOne(ctx, bson.D{{"_id", objID}}).Decode(result)
}

func (mongo *DataBase) Find(collectionName string, filter interface{}, result interface{}) error {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	collection := mongo.dataBase.Collection(collectionName)
	cur, err := collection.Find(ctx, filter)
	if err != nil {
		return err
	}
	defer cur.Close(ctx)

	if err := cur.All(ctx, result); err != nil {
		return err
	}

	return nil
}

func (mongo *DataBase) UpdateByID(collectionName string, id string, value interface{}) error {
	objID, err := primitive.ObjectIDFromHex(id)
	if err != nil {
		return err
	}

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	collection := mongo.dataBase.Collection(collectionName)
	_, err = collection.UpdateOne(ctx, bson.D{{"_id", objID}}, bson.D{{"$set", value}})
	return err
}

func (mongo *DataBase) DeleteByID(collectionName string, id string) error {
	objID, err := primitive.ObjectIDFromHex(id)
	if err != nil {
		return err
	}

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	collection := mongo.dataBase.Collection(collectionName)
	_, err = collection.DeleteOne(ctx, bson.D{{"_id", objID}})
	return err
}
