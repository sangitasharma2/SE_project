from typing import Any
from django.shortcuts import get_object_or_404, redirect, render
from .models import TransactionModel
from django.views.generic import CreateView, ListView
from django.views import View
from .constants import DEPOSIT, WITHDRAWAL, LOAN, LOAN_PAID, RECEIVED, TRANSFERRED
from django.contrib.auth.mixins import LoginRequiredMixin
from .forms import DepositForm, WithdrawForm, LoanRequestForm
from django.urls import reverse_lazy
from django.contrib import messages
from django.http import HttpResponse
from datetime import datetime
from django.db.models import Sum
from .utils.sendEmail import send_transaction_emails
from .forms import MoneyTransferForm
from accounts.models import UserBankAccountModel
from transactions.models import TransactionModel
# Create your views here.


class TransactionCreateMixin(LoginRequiredMixin, CreateView):
    template_name = "transactions/transaction_form.html"
    model = TransactionModel
    success_url = reverse_lazy("transaction_report")
    title = ""

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({
            "account": self.request.user.account
        })
        return kwargs

    def get_context_data(self, **kwargs: Any):
        context = super().get_context_data(**kwargs)
        context.update({
            "title": self.title
        })
        return context


class DepositMoneyView(TransactionCreateMixin):
    form_class = DepositForm
    title = 'Deposit'

    def get_initial(self):
        initial = {'transaction_type': DEPOSIT}
        return initial

    def form_valid(self, form):
        amount = form.cleaned_data.get('amount')
        account = self.request.user.account
        account.balance += amount
        account.save(
            update_fields=[
                'balance'
            ]
        )

        messages.success(self.request, f"""{"{:,.2f}".format(
            float(amount))}$ was deposited to your account successfully""")

        send_transaction_emails(
            self.request.user,
            self.request.user.email,
            f"Balance Deposited A/C {account.account_no}",
            f"""Your deposit request for ${amount} has successfully completed. After depsoit your total amount is{account.balance}""")

        return super().form_valid(form)


class WithdrawView(TransactionCreateMixin):
    form_class = WithdrawForm
    title = "Withdraw"

    def get_initial(self):
        initial = {'transaction_type': WITHDRAWAL}
        return initial

    def form_valid(self, form):
        amount = form.cleaned_data.get('amount')
        account = self.request.user.account

        if account.isBankrupt:
            messages.error(
                self.request, f"""Sorry your account has been Bankrupt""")
            return redirect("profile")

        account.balance -= amount
        account.save(
            update_fields=[
                'balance'
            ]
        )

        messages.success(self.request, f"""
        {"{:,.2f}".format(float(amount))}$ was withdrawn to your account successfully""")

        send_transaction_emails(
            self.request.user,
            self.request.user.email,
            f"Balance Withdrawal A/C {account.account_no}",
            f"""Your withdrawal request for ${amount} has successfully completed. After withdraw your total amount is ${account.balance}""")

        return super().form_valid(form)


class LoanRequestView(TransactionCreateMixin):
    form_class = LoanRequestForm
    title = "Request For Loan"

    def get_initial(self):
        initial = {'transaction_type': LOAN}
        return initial

    def form_valid(self, form):
        amount = form.cleaned_data.get('amount')
        account = self.request.user.account
        loan_count = TransactionModel.objects.filter(
            account=account, transaction_type=LOAN, loan_approve=True).count()

        if loan_count >= 3:
            return HttpResponse("You have cross the loan limits")

        messages.success(
            self.request,
            f"""Loan request for {"{:,.2f}".format(float(amount))}$ submitted successfully""")

        send_transaction_emails(
            self.request.user,
            self.request.user.email,
            f"Loan request for A/C {account.account_no}",
            f"""Your Loan request for ${amount} has successfully sent to the admin. Wait for admin approval. After getting admin approval you will get the loan and also ge the confirmation mail""")

        return super().form_valid(form)


class TransactionReportView(LoginRequiredMixin, ListView):
    template_name = "transactions/transaction_report.html"
    title = "Transactions"
    balance = 0
    model = TransactionModel

    def get_queryset(self):
        queryset = super().get_queryset().filter(account=self.request.user.account)

        start_date_str = self.request.GET.get('start_date')
        end_date_str = self.request.GET.get('end_date')

        if start_date_str and end_date_str:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()

            queryset = queryset.filter(
                timestamp__date__gte=start_date, timestamp__date__lte=end_date)

            self.balance = TransactionModel.objects.filter(
                timestamp__date__gte=start_date, timestamp__date__lte=end_date
            ).aggregate(Sum('amount'))['amount__sum']
        else:
            self.balance = self.request.user.account.balance

        return queryset.distinct()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'account': self.request.user.account
        })

        return context


class PayLoanView(LoginRequiredMixin, View):
    def get(self, request, loan_id):
        loan = get_object_or_404(TransactionModel, id=loan_id)

        if loan.loan_approve:
            user_account = loan.account

            if loan.amount <= user_account.balance:
                user_account.balance -= loan.amount
                loan.balance_after_transaction = user_account.balance
                user_account.save()
                loan.transaction_type = LOAN_PAID
                loan.save()
                messages.success(
                    self.request, "Loan paid successfully")
                return redirect("transaction_report")
            else:
                messages.error(
                    self.request, "Loan amount is greater than available balance")
                return redirect("transaction_report")


class LoanListView(LoginRequiredMixin, ListView):
    model = TransactionModel
    template_name = "transactions/loan_request.html"
    context_object_name = "loans"

    def get_queryset(self):
        user_account = self.request.user.account
        queryset = TransactionModel.objects.filter(
            account=user_account, transaction_type=LOAN)
        return queryset


class MoneyTransferView(LoginRequiredMixin, View):

    def get(self, request):
        return render(request, "transactions/money_transfer.html", {"form": MoneyTransferForm, "title" : "Money Transfer"})

    def post(self,request):
        form = MoneyTransferForm(request.POST)
        
        if form.is_valid():
            amount = form.cleaned_data.get("amount")
            account_no = form.cleaned_data.get("account_no")
            
            isBankAccountExists = UserBankAccountModel.objects.filter(account_no=account_no).count()
            if isBankAccountExists :
                to_account = UserBankAccountModel.objects.get(account_no=account_no)
                request.user.account.balance -= amount
                to_account.balance += amount
               
                request.user.account.save()
                to_account.save()

                TransactionModel.objects.create(
                    account = request.user.account,
                    amount = amount,
                    balance_after_transaction = request.user.account.balance,
                    transaction_type = TRANSFERRED,
                )
                TransactionModel.objects.create(
                    account = to_account,
                    amount = amount,
                    balance_after_transaction = to_account.balance,
                    transaction_type = RECEIVED,
                )
                send_transaction_emails(
                request.user,
                request.user.email,
                f"Successfully money Transferred to A/C {to_account.account_no}",
                f"""Your ${amount} of money transfer request has been done and your current balance is {request.user.account.balance}""")

                send_transaction_emails(
                to_account.account,
                to_account.account.email,
                f"Money received from A/C {request.user.account.account_no}",
                f"""Money ${amount} has been received from {request.user.account.account_no} and your current balance is {to_account.balance}""")

                messages.success(request, "Money has been transferred successfully")
                return redirect("transaction_report")
            else :
                messages.error(request, "Sorry no Bank account was found on this number!!")

        return render(request, "transactions/money_transfer.html", {"form": MoneyTransferForm, "title" : "Money Transfer"})

