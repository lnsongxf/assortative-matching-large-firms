import numpy as np
from scipy import integrate, special
import sympy as sym

import models

# represent endogenous variables mu and theta as a deferred vector
V = sym.DeferredVector('V')


class ShootingSolver(object):
    """Solves a model using forward shooting."""

    __numeric_jacobian = None

    __numeric_profit = None

    __numeric_system = None

    __numeric_wage = None

    __integrator = None

    _modules = [{'ImmutableMatrix': np.array, 'erf': special.erf}, 'numpy']

    def __init__(self, model):
        """
        Create an instance of the ShootingSolver class.

        """
        self.model = model

    @property
    def _numeric_jacobian(self):
        """
        Vectorized function for numerical evaluation of model Jacobian.

        :getter: Return the current function for evaluating the Jacobian.
        :type: function

        """
        if self.__numeric_jacobian is None:
            self.__numeric_jacobian = sym.lambdify(self._symbolic_args,
                                                   self._symbolic_jacobian,
                                                   self._modules)
        return self.__numeric_jacobian

    @property
    def _numeric_profit(self):
        """
        Vectorized function for numerical evaluation of profits.

        :getter: Return the current function for evaluating profits.
        :type: function

        """
        if self.__numeric_profit is None:
            self.__numeric_profit = sym.lambdify(self._symbolic_args,
                                                 self._symbolic_profit,
                                                 self._modules)
        return self.__numeric_profit

    @property
    def _numeric_system(self):
        """
        Vectorized function for numerical evaluation of model system.

        :getter: Return the current function for evaluating the system.
        :type: function

        """
        if self.__numeric_system is None:
            self.__numeric_system = sym.lambdify(self._symbolic_args,
                                                 self._symbolic_system,
                                                 self._modules)
        return self.__numeric_system

    @property
    def _numeric_wage(self):
        """
        Vectorized function for numerical evaluation of wages.

        :getter: Return the current function for evaluating wages.
        :type: function

        """
        if self.__numeric_wage is None:
            self.__numeric_wage = sym.lambdify(self._symbolic_args,
                                               self._symbolic_wage,
                                               self._modules)
        return self.__numeric_wage

    @property
    def _symbolic_args(self):
        """
        Symbolic arguments used when lambdifying symbolic Jacobian and system.

        :getter: Return the list of symbolic arguments.
        :type: list

        """
        return self._symbolic_variables + self._symbolic_params

    @property
    def _symbolic_equations(self):
        """
        Symbolic expressions defining the right-hand side of a system of ODEs.

        :getter: Return the list of symbolic expressions.
        :type: list

        """
        return [self.model.matching.mu_prime, self.model.matching.theta_prime]

    @property
    def _symbolic_jacobian(self):
        """
        Symbolic expressions defining the Jacobian of a system of ODEs.

        :getter: Return the symbolic Jacobian.
        :type: sympy.Basic

        """
        return self._symbolic_system.jacobian([V[0], V[1]])

    @property
    def _symbolic_params(self):
        """
        Symbolic parameters passed as arguments when lambdifying symbolic
        Jacobian and system.

        :getter: Return the list of symbolic parameter arguments.
        :type: list

        """
        return sym.var(list(self.model.params.keys()))

    @property
    def _symbolic_profit(self):
        """
        Symbolic expression defining profit.

        :getter: Return the symbolic expression for profits.
        :type: sympy.Basic

        """
        profit = self.model.matching.profit
        return profit.subs({'mu': V[0], 'theta': V[1]})

    @property
    def _symbolic_system(self):
        """
        Symbolic matrix defining the right-hand side of a system of ODEs.

        :getter: Return the symbolic matrix.
        :type: sympy.Matrix

        """
        system = sym.Matrix(self._symbolic_equations)
        return system.subs({'mu': V[0], 'theta': V[1]})

    @property
    def _symbolic_variables(self):
        """
        Symbolic variables passed as arguments when lambdifying symbolic
        Jacobian and system.

        :getter: Return the list of symbolic variable arguments.
        :type: list

        """
        return [self.model.workers.var, V]

    @property
    def _symbolic_wage(self):
        """
        Symbolic expression defining wages.

        :getter: Return the symbolic expression for wages.
        :type: sympy.Basic

        """
        wage = self.model.matching.wage
        return wage.subs({'mu': V[0], 'theta': V[1]})

    @property
    def model(self):
        """
        Instance of the models.Model class to be solved via forward shooting.

        :getter: Return the current models.Model instance.
        :setter: Set a new models.Model instance.
        :type: models.Model

        """
        return self._model

    @model.setter
    def model(self, model):
        """Set a new Model attribute."""
        self._model = self._validate_model(model)
        self._clear_cache()

    @property
    def solution(self):
        return self._solution

    @solution.setter
    def solution(self, value):
        self._solution = value

    @property
    def integrator(self):
        """
        Integrator for solving a system of ordinary differential equations.

        :getter: Return the current integrator.
        :type: scipy.integrate.ode

        """
        if self.__integrator is None:
            self.__integrator = integrate.ode(f=self.evaluate_rhs,
                                              jac=self.evaluate_jacobian)
        return self.__integrator

    @staticmethod
    def _almost_zero_profit(profit, tol):
        return profit <= tol

    @staticmethod
    def _almost_zero_wage(wage, tol):
        return wage <= tol

    def _clear_cache(self):
        """Clear cached functions used for numerical evaluation."""
        self.__numeric_jacobian = None
        self.__numeric_profit = None
        self.__numeric_system = None
        self.__numeric_wage = None
        self.__integrator = None

    def _converged_firms(self, bound, tol):
        """Check whether solution component for firms has converged."""
        if abs(self.integrator.y[0] - bound) <= tol:
            converged = True
        else:
            converged = False
        return converged

    def _converged_workers(self, bound, tol):
        """Check whether solution component for workers has converged."""
        if abs(self.integrator.t - bound) <= tol:
            converged = True
        else:
            converged = False
        return converged

    def _exhausted_firms(self, bound, tol):
        """Check whether firms have been exhausted."""
        if self.integrator.y[0] - bound < -tol:
            exhausted = True
        else:
            exhausted = False
        return exhausted

    def _exhausted_workers(self, bound, tol):
        """Check whether workers have been exhausted."""
        if self.model.assortativity == 'positive':
            if self.integrator.t - bound < -tol:
                exhausted = True
            else:
                exhausted = False
        else:
            if self.integrator.t - bound > tol:
                exhausted = True
            else:
                exhausted = False

        return exhausted

    def _guess_firm_size_upper_too_low(self, bound, tol):
        """Check whether guess for upper bound for firm size is too low."""
        return abs(self.integrator.y[1] - bound) <= tol

    def _reset_negative_assortative_solution(self, firm_size):
        """
        Reset the initial condition for the integrator and re-initialze
        the solution array for model with negative assortative matching.

        Parameters
        ----------
        firm_size : float

        """
        # reset the initial condition for the integrator
        x_lower, y_upper = self.model.workers.lower, self.model.firms.upper
        initial_V = np.array([y_upper, firm_size])
        self.integrator.set_initial_value(initial_V, x_lower)

        # reset the putative equilibrium solution
        wage = self.evaluate_wage(x_lower, initial_V)
        profit = self.evaluate_profit(x_lower, initial_V)
        self.solution = np.hstack((x_lower, initial_V, wage, profit))

    def _reset_positive_assortative_solution(self, firm_size):
        """
        Reset the initial condition for the integrator and re-initialze
        the solution array for model with positive assortative matching.

        Parameters
        ----------
        firm_size : float

        """
        # reset the initial condition for the integrator
        x_upper, y_upper = self.model.workers.upper, self.model.firms.upper
        initial_V = np.array([y_upper, firm_size])
        self.integrator.set_initial_value(initial_V, x_upper)

        # reset the putative equilibrium solution
        wage = self.evaluate_wage(x_upper, initial_V)
        profit = self.evaluate_profit(x_upper, initial_V)
        self.solution = np.hstack((x_upper, initial_V, wage, profit))

    def _solve_negative_assortative_matching(self, guess_firm_size_upper, tol,
                                             number_knots, integrator, **kwargs):
        """Solve for negative assortative matching equilibrium."""

        # relevant bounds
        x_lower = self.model.workers.lower
        x_upper = self.model.workers.upper
        y_lower = self.model.firms.lower

        # initialize integrator
        self.integrator.set_integrator(integrator, **kwargs)

        # initialize the solution
        firm_size_lower = 0.0
        firm_size_upper = guess_firm_size_upper
        guess_firm_size = 0.5 * (firm_size_upper + firm_size_lower)
        self._reset_negative_assortative_solution(guess_firm_size)

        # step size insures that never step beyond x_lower
        step_size = (x_upper - x_lower) / (number_knots - 1)

        while self.integrator.successful():

            if self._guess_firm_size_upper_too_low(guess_firm_size_upper, tol):
                mesg = ("Failure! Need to increase initial guess for upper " +
                        "bound on firm size!")
                print(mesg)
                break

            #if self._check_matching_conditions():
            #    pass

            # walk the system forward one step
            self.integrator.integrate(self.integrator.t + step_size)

            # unpack the components of the new step
            x, V = self.integrator.t, self.integrator.y
            mu, theta = V
            assert theta > 0.0, "Firm size should be non-negative!"

            # update the putative equilibrium solution
            wage = self.evaluate_wage(x, V)
            profit = self.evaluate_profit(x, V)
            step = np.hstack((x, V, wage, profit))
            self.solution = np.vstack((self.solution, step))

            if self._exhausted_workers(x_upper, tol):
                mesg = ("Initial guess of {} for firm size is too high!" +
                        " (run out of workers) ")
                print(mesg.format(guess_firm_size))
                firm_size_upper = guess_firm_size
                guess_firm_size = 0.5 * (firm_size_upper + firm_size_lower)
                self._reset_negative_assortative_solution(guess_firm_size)

            elif self._exhausted_firms(y_lower, tol):
                mesg = ("Initial guess of {} for firm size is too low!" +
                        "(run out of firms)")
                print(mesg.format(guess_firm_size))
                firm_size_lower = guess_firm_size
                guess_firm_size = 0.5 * (firm_size_upper + firm_size_lower)
                self._reset_negative_assortative_solution(guess_firm_size)

            elif self._converged_workers(x_upper, tol):
                if self._converged_firms(y_lower, tol):
                    mesg = ("Success! Found equilibrium where all workers " +
                            "and firms are matched")
                    print(mesg)
                    break

                elif ((not self._exhausted_firms(y_lower, tol)) and
                      self._almost_zero_profit(profit, tol)):
                    mesg = "Success! Found equilibrium with excess firms."
                    print(mesg)
                    break

                elif((not self._exhausted_firms(y_lower, tol)) and
                     (not self._almost_zero_profit(profit, tol))):
                    mesg = ("Firms about and positive profits to be had: " +
                            "initial guess of {} for firm size is too high!")
                    print(mesg.format(guess_firm_size))
                    firm_size_upper = guess_firm_size
                    guess_firm_size = 0.5 * (firm_size_upper + firm_size_lower)
                    self._reset_negative_assortative_solution(guess_firm_size)

                else:
                    mesg = ("Exhausted all firms: initial guess of {} for " +
                            "firm size is too low!")
                    print(mesg.format(guess_firm_size))
                    firm_size_lower = guess_firm_size
                    guess_firm_size = 0.5 * (firm_size_upper + firm_size_lower)
                    self._reset_negative_assortative_solution(guess_firm_size)

            elif self._converged_firms(y_lower, tol):
                if self._converged_workers(x_upper, tol):
                    assert "This case should have already been handled above!"

                elif ((not self._exhausted_workers(x_upper, tol)) and
                      self._almost_zero_wage(wage, tol)):
                    mesg = "Success! Found equilibrium with excess workers."
                    print(mesg)
                    break

                elif ((not self._exhausted_workers(x_upper, tol)) and
                      (not self._almost_zero_wage(wage, tol))):
                    mesg = ("Workers still unmatched but wages are not zero: "
                            "initial guess of {} for firm size is too low.")
                    print(mesg.format(guess_firm_size))
                    firm_size_lower = guess_firm_size
                    guess_firm_size = 0.5 * (firm_size_upper + firm_size_lower)
                    self._reset_negative_assortative_solution(guess_firm_size)

                else:
                    mesg = ("Exhausted all workers: initial guess of {} for " +
                            "firm size is too high!")
                    print(mesg.format(guess_firm_size))
                    firm_size_upper = guess_firm_size
                    guess_firm_size = 0.5 * (firm_size_upper + firm_size_lower)
                    self._reset_negative_assortative_solution(guess_firm_size)

            else:
                continue

    def _solve_positive_assortative_matching(self, guess_firm_size_upper, tol,
                                             number_knots, integrator, **kwargs):
        """Solve for positive assortative matching equilibrium."""

        # relevant bounds
        x_lower = self.model.workers.lower
        x_upper = self.model.workers.upper
        y_lower = self.model.firms.lower

        # initialize integrator
        self.integrator.set_integrator(integrator, **kwargs)

        # initialize the solution
        firm_size_lower = 0.0
        firm_size_upper = guess_firm_size_upper
        guess_firm_size = 0.5 * (firm_size_upper + firm_size_lower)
        self._reset_positive_assortative_solution(guess_firm_size)

        # step size insures that never step beyond x_lower
        step_size = (x_upper - x_lower) / (number_knots - 1)

        while self.integrator.successful():

            if self._guess_firm_size_upper_too_low(guess_firm_size_upper, tol):
                mesg = ("Failure! Need to increase initial guess for upper " +
                        "bound on firm size!")
                print(mesg)
                break

            # walk the system forward one step
            self.integrator.integrate(self.integrator.t - step_size)

            # unpack the components of the new step
            x, V = self.integrator.t, self.integrator.y
            mu, theta = V
            assert theta > 0.0, "Firm size should be non-negative!"

            # update the putative equilibrium solution
            wage = self.evaluate_wage(x, V)
            profit = self.evaluate_profit(x, V)
            step = np.hstack((x, V, wage, profit))
            self.solution = np.vstack((self.solution, step))

            if self._converged_workers(x_lower, tol) and self._converged_firms(y_lower, tol):
                mesg = ("Success! All workers and firms are matched")
                print(mesg)
                break

            elif (not self._converged_workers(x_lower, tol)) and self._exhausted_firms(y_lower, tol):
                mesg = "Exhausted firms: initial guess of {} for firm size is too low."
                print(mesg.format(guess_firm_size))
                firm_size_lower = guess_firm_size
                guess_firm_size = 0.5 * (firm_size_upper + firm_size_lower)
                self._reset_positive_assortative_solution(guess_firm_size)

            elif self._converged_workers(x_lower, tol) and self._exhausted_firms(y_lower, tol):
                mesg = "Exhausted firms: Initial guess of {} for firm size was too low!"
                print(mesg.format(guess_firm_size))
                firm_size_lower = guess_firm_size
                guess_firm_size = 0.5 * (firm_size_upper + firm_size_lower)
                self._reset_positive_assortative_solution(guess_firm_size)

            elif self._converged_workers(x_lower, tol) and (not self._exhausted_firms(y_lower, tol)):
                mesg = "Exhausted workers: initial guess of {} for firm size is too high!"
                print(mesg.format(guess_firm_size))
                firm_size_upper = guess_firm_size
                guess_firm_size = 0.5 * (firm_size_upper + firm_size_lower)
                self._reset_positive_assortative_solution(guess_firm_size)

            else:
                continue

    @staticmethod
    def _validate_model(model):
        """Validate the model attribute."""
        if not isinstance(model, models.Model):
            mesg = ("Attribute 'model' must have type models.Model, not {}.")
            raise AttributeError(mesg.format(model.__class__))
        else:
            return model

    def evaluate_jacobian(self, x, V):
        r"""
        Numerically evaluate model Jacobian.

        Parameters
        ----------
        x : float
            Value for worker skill (i.e., the independent variable).
        V : numpy.array (shape=(2,))
            Array of values for the dependent variables with ordering:
            :math:`[\mu, \theta]`.

        Returns
        -------
        jac : numpy.array (shape=(2,2))
            Jacobian matrix of partial derivatives.

        """
        jac = self._numeric_jacobian(x, V, **self.model.params)
        return jac

    def evaluate_profit(self, x, V):
        r"""
        Numerically evaluate profit for a firm with productivity V[0] and size
        V[1] when matched with a worker with skill x.

        Parameters
        ----------
        x : float
            Value for worker skill (i.e., the independent variable).
        V : numpy.array (shape=(2,))
            Array of values for the dependent variables with ordering:
            :math:`[\mu, \theta]`.

        Returns
        -------
        profit : float
            Firm's profit.

        """
        profit = self._numeric_profit(x, V, **self.model.params)
        assert profit > 0.0, "Profit should be non-negative!"
        return profit

    def evaluate_rhs(self, x, V):
        r"""
        Numerically evaluate right-hand side of the system of ODEs.

        Parameters
        ----------
        x : float
            Value for worker skill (i.e., the independent variable).
        V : numpy.array (shape=(2,))
            Array of values for the dependent variables with ordering:
            :math:`[\mu, \theta]`.

        Returns
        -------
        rhs : numpy.array (shape=(2,))
            Right hand side of the system of ODEs.

        """
        rhs = self._numeric_system(x, V, **self.model.params).ravel()
        return rhs

    def evaluate_wage(self, x, V):
        r"""
        Numerically evaluate wage for a worker with skill level x when matched
        to a firm with productivity V[0] with size V[1].

        Parameters
        ----------
        x : float
            Value for worker skill (i.e., the independent variable).
        V : numpy.array (shape=(2,))
            Array of values for the dependent variables with ordering:
            :math:`[\mu, \theta]`.

        Returns
        -------
        wage : float
            Worker's wage.

        """
        wage = self._numeric_wage(x, V, **self.model.params)
        assert wage > 0.0, "Wage should be non-negative!"
        return wage

    def solve(self, guess_firm_size_upper, tol=1e-6, number_knots=100,
              integrator='dopri5', **kwargs):
        if self.model.assortativity == 'positive':
            self._solve_positive_assortative_matching(guess_firm_size_upper,
                                                      tol, number_knots,
                                                      integrator, **kwargs)
        else:
            self._solve_negative_assortative_matching(guess_firm_size_upper,
                                                      tol, number_knots,
                                                      integrator, **kwargs)
