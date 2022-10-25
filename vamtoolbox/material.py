from cmath import isnan
import numpy as np
import matplotlib.pyplot as plt
import time
import warnings

class ResponseModel:

    __default_gen_log_fun = {"A": 0, "K": 1, "B": 25, "M": 0.5, "nu": 1}
    __default_linear = {"M":1, "C":0} 
    __default_interpolation = {"interp_min": 0, "interp_max":1, "n_pts": 512}
    
    def __init__(self,type : str = "interpolation", form :str = "gen_log_fun", **kwargs):
        """
        Parameters
        ----------
        type : str ("analytical", "interpolation")
            Select analytical function evaluation or interpolate on pre-built interpolant arrays. 
            Interpolation method handles edge cases of input explicitly and hence is more robust.

        form : str ("gen_log_fun", "linear", "identity", "freeform")

        A : float, optional
            parameter in generalized logistic function (Richard's curve)
            Left asymptote

        K : float, optional
            parameter in generalized logistic function (Richard's curve)
            Right asymptote

        B : float, optional
            parameter in generalized logistic function (Richard's curve)
            Steepness of the curve

        M : float, optional
            parameter in generalized logistic function (Richard's curve)
            M shifts the curve left or right. It is the location of inflextion point when nu = 1. 

        nu : float, optional
            parameter in generalized logistic function (Richard's curve)
            Influence location of maximum slope relative to the two asymptotes. "Skew" the curve towards either end.

        M : float, optional
            parameter in linear (affine) function
            M is the slope of the curve: map = M*f + C

        C : float, optional
            parameter in linear (affine) function
            M is the y-intercept of the curve: map = M*f + C        

        """
        self.type = type
        self.form = form

        if self.type == "analytical":
            if self.form == "gen_log_fun":
                self.map = self.__map_glf__
                self.dmapdf = self.__dmapdf_glf__
                self.map_inv = self.__map_inv_glf__
                self.params = self.__default_gen_log_fun.copy() #Shallow copy avoid editing dict "__default_gen_log_fun" in place 
                self.params.update(kwargs) #up-to-date parameters. Default dict is not updated
                
            elif self.form == "linear":  
                self.map = self.__map_lin__
                self.dmapdf = self.__dmapdf_lin__
                self.map_inv = self.__map_inv_lin__
                self.params = self.__default_linear.copy() #Shallow copy avoid editing dict "__default_linear" in place 
                self.params.update(kwargs) #up-to-date parameters. Default dict is not updated

            elif self.form == "identity":
                self.map = self.__map_id__
                self.dmapdf = self.__dmapdf_id__
                self.map_inv = self.__map_inv_id__

            else:
                raise Exception("Form: Other analytical functions are not supported yet.")

        elif self.type == "interpolation":
            #Interpolation method stores three 1-D arrays as interpolant and query them upon each mapping call.
            #Stored arrays : (1)Sampling point on f, (2)corresponding forward map values, and (3)the first derviative of forward map.
            #All arrays are of the same size. The inverse mapping use (1) and (2) for memory efficiency and avoid singularity problem at asymptotes.

            #function alias
            self.map = self.__map_interp__
            self.dmapdf = self.__dmapdf_interp__
            self.map_inv = self.__map_inv_interp__ #Inverse mapping uses the same set of data generated for forward mapping.
            self.params = self.__default_interpolation.copy() #Shallow copy avoid editing dict "__default_interpolation" in place 
            
            #build or import interpolant dataset 
            if self.form == "gen_log_fun":
                self.params.update(self.__default_gen_log_fun) #Add relevant parameters
                self.params.update(kwargs) #up-to-date parameters. Default dict is not updated

                #build interpolant arrays
                self.interp_f_0 = np.linspace(self.params["interp_min"], self.params["interp_max"], self.params["n_pts"])
                self.interp_map_0 = self.__map_glf__(self.interp_f_0)
                self.interp_dmapdf_0 = self.__dmapdf_glf__(self.interp_f_0)


            elif self.form == "linear":
                self.params.update(self.__default_linear) #Add relevant parameters
                self.params.update(kwargs) #up-to-date parameters. Default dict is not updated

                #build interpolant arrays
                self.interp_f_0 = np.linspace(self.params["interp_min"], self.params["interp_max"], self.params["n_pts"])
                self.interp_map_0 = self.__map_lin__(self.interp_f_0)
                self.interp_dmapdf_0 = self.__dmapdf_lin__(self.interp_f_0)


            elif self.form == "identity":
                self.params.update(kwargs) #up-to-date parameters. Default dict is not updated

                #build interpolant arrays
                self.interp_f_0 = np.linspace(self.params["interp_min"], self.params["interp_max"], self.params["n_pts"])
                self.interp_map_0 = self.__map_id__(self.interp_f_0)
                self.interp_dmapdf_0 = self.__dmapdf_id__(self.interp_f_0)


            elif self.form == "freeform": #Directly import data instead of generating.
                self.interp_f_0 = kwargs.get('interp_f_0',None) #Input data points are designated with 0 subscript
                self.interp_map_0 = kwargs.get('interp_map_0',None)  #Input data points are designated with 0 subscript

                #Check inputs
                if (len(self.interp_f_0.shape) > 1) or (len(self.interp_map_0.shape) > 1):
                    raise Exception("Imported data for material response curve should be 1D. Check 'interp_f_0' and 'interp_map_0'.")
                if (self.interp_f_0.shape) != (self.interp_map_0.shape):
                    raise Exception("Size mismatch between 'interp_f_0' and 'interp_map_0'.")

                #Extending the diff curve by assuming continuity of 1st derivative at the end of the curve
                self.interp_dmapdf_0 = np.diff(self.interp_map_0, n=1, append = (self.interp_map_0[-1] + (self.interp_map_0[-1]-self.interp_map_0[-2]))) 
                #Alternative solution to the differed array size is simply using shorter arrays.

            else:
                raise Exception("Other interpolation functions are not supported yet.")                

        else:
            raise Exception("Numerical mapping is not supported yet.")

    #=================================Analytic: Generalized logistic function================================================

    #Definition of generalized logistic function: https://en.wikipedia.org/wiki/Generalised_logistic_function
    def __map_glf__(self, f : np.ndarray):
        numerator = self.params["K"] - self.params["A"]

        self.cached_exp = np.exp(-self.params["B"]*(f-self.params["M"])) #cache result for later computation of derivative
        denominator = (1+self.cached_exp)**(1/self.params["nu"])
        
        self.cached_map = self.params["A"] + (numerator/denominator)  #cache result for later use
        return self.cached_map


    def __dmapdf_glf__(self, f : np.ndarray, use_cached_result : bool = False):
        #This function allows pre-computed results to be used to avoid duplicated computations
        #If 'map' is already executed for the exact current input f, use of cached results avoid recomputing the forward map in derivative evaluation.

        coef_1 = ((1/(self.params["K"] - self.params["A"]))**self.params["nu"])
        coef_2 = (self.params["B"]/self.params["nu"])
        if use_cached_result:
            coef_3 = (self.cached_map-self.params["A"])**(self.params["nu"]+1)
            exponential = self.cached_exp
        else:
            coef_3 = (self.__map_glf__(f)-self.params["A"])**(self.params["nu"]+1)
            exponential = np.exp(-self.params["B"]*(f-self.params["M"]))

        self.cached_dmapdf = coef_1*coef_2*coef_3*exponential 
        return self.cached_dmapdf

    def __map_inv_glf__(self, mapped : np.ndarray):
        
        numerator = -np.log(((self.params["K"] - self.params["A"])/(mapped - self.params["A"]))**self.params["nu"] - 1) #Given C=1 and Q=1 --> log(Q)=log(1)=0
        f = (numerator/self.params["B"]) + self.params["M"]

        return f

    #=================================Analytic: Linear (affine) function=====================================================
    #Definition of linear function: mapped = M*f + C
    def __map_lin__(self, f : np.ndarray):
        self.cached_map = self.params["M"]*f + self.params["C"]
        return self.cached_map

    def __dmapdf_lin__(self, f : np.ndarray, use_cached_result : bool = False):
        return np.ones_like(f)*self.params["M"]

    def __map_inv_lin__(self, mapped : np.ndarray):
        return (mapped-self.params["C"])/self.params["M"]


    #=================================Analytic: Identity function============================================================
    #Definition of identity: mapped = f
    def __map_id__(self, f : np.ndarray):
        self.cached_map = f
        return self.cached_map

    def __dmapdf_id__(self, f : np.ndarray, use_cached_result : bool = False):
        return np.ones_like(f)

    def __map_inv_id__(self, mapped : np.ndarray):
        return mapped

    #=================================Interpolation==========================================================================
    def __map_interp__(self, f : np.ndarray):
        """
        Map optical dose to response via interpolation. 
        More robust for asymptote values and potentially faster than computing exponentials in generalized logistic function.
        """
        return np.interp(f, self.interp_f_0, self.interp_map_0, left = self.interp_map_0[0], right = self.interp_map_0[-1]) #Extrapolation points are taken as nearest neighbor, same as default


    def __dmapdf_interp__(self, f : np.ndarray):
        """
        Map optical dose to response 1st derivative via interpolation. 
        """
        return np.interp(f, self.interp_f_0, self.interp_dmapdf_0, left = self.interp_dmapdf_0[0], right = self.interp_dmapdf_0[-1]) #Extrapolation points are taken as nearest neighbor, same as default

    def __map_inv_interp__(self, mapped : np.ndarray):
        """
        Map material response back to optical dose via interpolation. 
        """
        return np.interp(mapped, self.interp_map_0, self.interp_f_0, left = self.interp_f_0[0], right = self.interp_f_0[-1]) #Extrapolation points are taken as nearest neighbor, same as default


    #=================================Utilities==========================================================================
    def plotMap(self, lb = 0, ub = 1, n_pts=512, block=False, show = True):

        f_test = np.linspace(lb,ub,n_pts)
        mapped_f_test = self.map(f_test)
        # plt.figure()
        plt.plot(f_test, mapped_f_test)
        if block == False:
            plt.ion()
        if show == True:
            plt.show()


    def plotDmapDf(self, lb = 0, ub = 1, n_pts=512, block=False, show = True):

        f_test = np.linspace(lb,ub,n_pts)
        mapped_f_test = self.dmapdf(f_test)
        # plt.figure()
        plt.plot(f_test, mapped_f_test)
        if block == True:
            plt.ioff()
        else:
            plt.ion()

        if show == True:
            plt.show()    

    def plotMapInv(self, lb = 0, ub = 1, n_pts=512, block=False, show = True):

        map_test = np.linspace(lb,ub,n_pts)
        f_test = self.map_inv(map_test)
        # plt.figure()
        plt.plot(map_test, f_test)
        if block == True:
            plt.ioff()
        else:
            plt.ion()

        if show == True:
            plt.show()    

    def checkResponseTarget(self, f_T : np.ndarray):
        #Check if the response target is reachable with non-negative real inputs, and if it contains inf or nan.
        #Get target range
        f_T_min = np.amin(f_T)
        f_T_max = np.amax(f_T)

        validity = True

        #Check upper limit of response function (only for logistic function)
        if self.form == "gen_log_fun":
            if f_T_max > self.params["K"]:
                warnings.warn("Maximum response target is greater than right asymptotic value of response function.")
                validity = False
        
        #Check lower limit of response function (for all functional forms), up to 1% tolerance
        if (f_T_min < self.map(0)) and ~(np.isclose(f_T_min, self.map(0), atol= 0.01*f_T_max)):
            warnings.warn("Minimum response target is lower than response at zero optical dose.")
            validity = False

        #Check for boundedness
        if np.isinf(f_T).any():
            warnings.warn("Response target contains infinite value(s).")
            validity = False

        #Check for numeric values
        if np.isnan(f_T).any():
            warnings.warn("Response target contains nan value(s).")
            validity = False

        return validity



## Test

if __name__ == "__main__":

    plt.figure()
    plt.title('Generalized logistic function with varying B')
    plt.grid(True)
    test_rm = ResponseModel(B=10)
    test_rm.plotMap(show = False)
    print(test_rm.params)

    test_rm = ResponseModel(B=25)
    test_rm.plotMap(show = False)
    print(test_rm.params)

    test_rm = ResponseModel(B=50)
    test_rm.plotMap(show = False)
    print(test_rm.params)

    plt.figure()
    plt.title('Generalized logistic function with varying nu')
    plt.grid(True)
    test_rm = ResponseModel(nu=0.2)
    test_rm.plotMap(show = False)
    print(test_rm.params)

    test_rm = ResponseModel(nu=1)
    test_rm.plotMap(show = False)
    print(test_rm.params)

    test_rm = ResponseModel(nu=5)
    test_rm.plotMap(show = False)
    print(test_rm.params)

    plt.figure()
    plt.title('Derivative of generalized logistic function with varying B')
    plt.grid(True)
    test_rm = ResponseModel(B=10)
    test_rm.plotDmapDf(show = False)
    print(test_rm.params)

    test_rm = ResponseModel(B=25)
    test_rm.plotDmapDf(show = False)
    print(test_rm.params)

    test_rm = ResponseModel(B=50)
    test_rm.plotDmapDf(show = False)
    print(test_rm.params)

    plt.figure()
    plt.title('Derivative of generalized logistic function with varying nu')
    plt.grid(True)
    test_rm = ResponseModel(nu=0.2)
    test_rm.plotDmapDf(show = False)
    print(test_rm.params)

    test_rm = ResponseModel(nu=1)
    test_rm.plotDmapDf(show = False)
    print(test_rm.params)

    test_rm = ResponseModel(nu=5)
    test_rm.plotDmapDf(show = False)
    print(test_rm.params)

    #Check inversion function
    plt.figure()
    plt.title('Inverse of generalized logistic function with varying B')
    plt.grid(True)
    test_rm = ResponseModel(B=10)
    test_rm.plotMapInv(show = False)
    print(test_rm.params)

    test_rm = ResponseModel(B=25)
    test_rm.plotMapInv(show = False)
    print(test_rm.params)

    test_rm = ResponseModel(B=50)
    test_rm.plotMapInv(show = False)
    print(test_rm.params)

    plt.figure()
    plt.title('Inverse of generalized logistic function with varying nu')
    plt.grid(True)
    test_rm = ResponseModel(nu=0.2)
    test_rm.plotMapInv(show = False)
    print(test_rm.params)

    test_rm = ResponseModel(nu=1)
    test_rm.plotMapInv(show = False)
    print(test_rm.params)

    test_rm = ResponseModel(nu=5)
    test_rm.plotMapInv(show = False)
    print(test_rm.params)

    plt.show()
    input()
