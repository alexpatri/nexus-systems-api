package utils

import (
	"github.com/sethvargo/go-password/password"
	"golang.org/x/crypto/bcrypt"
)

func GeneratePassword(size, digitsQtd, symbolsQtd int) (string, error) {
	return password.Generate(size, digitsQtd, symbolsQtd, false, false)
}

func HashPassword(password string) (string, error) {
	bytes, err := bcrypt.GenerateFromPassword([]byte(password), 14)
	return string(bytes), err
}

func VerifyPassword(password, hash string) bool {
	err := bcrypt.CompareHashAndPassword([]byte(hash), []byte(password))
	return err == nil
}
