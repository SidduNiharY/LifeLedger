from enum import StrEnum


class Category(StrEnum):
    FOOD = "Food"
    TRAVEL = "Travel"
    RENT = "Rent"
    BILLS = "Bills"
    SHOPPING = "Shopping"
    EMI = "EMI"
    SUBSCRIPTIONS = "Subscriptions"
    TRANSFER = "Transfer"
    INCOME = "Income"
    OTHER = "Other"


# Left out of spend totals so card spends and bill payments are not counted twice.
SPEND_EXCLUDED = frozenset({Category.TRANSFER, Category.INCOME})

CATEGORY_DESCRIPTIONS: dict[Category, str] = {
    Category.FOOD: (
        "Eating out, food delivery, cafes and groceries (e.g. Swiggy, Zomato, BigBasket)."
    ),
    Category.TRAVEL: "Cabs, autos, fuel, metro, trains, flights, buses, hotels and tolls.",
    Category.RENT: "House rent and maintenance paid to a landlord or society.",
    Category.BILLS: "Electricity, water, gas, mobile, broadband, DTH and other utility bills.",
    Category.SHOPPING: "Online and offline retail: clothes, electronics, household items.",
    Category.EMI: "Loan EMIs and repayments.",
    Category.SUBSCRIPTIONS: (
        "Recurring digital services and memberships (streaming, software, gym)."
    ),
    Category.TRANSFER: (
        "Money moved between your own accounts, credit card bill payments, investments and savings."
    ),
    Category.INCOME: "Money received: salary, interest, refunds, money from others.",
    Category.OTHER: "Anything that fits none of the above.",
}
