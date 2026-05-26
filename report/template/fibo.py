"""Exemple tres simple conserve dans le modele de rapport."""

def fibo(n):
    """Calcule la suite de Fibonacci par recursion simple."""
    if n < 0:
        print("Incorrect input")
    elif n == 0:
        return 0
    elif n == 1 or n == 2:
        return 1
    else:
        return fibo(n-1) + fibo(n-2)
