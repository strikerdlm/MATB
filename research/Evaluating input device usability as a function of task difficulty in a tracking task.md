

# Ergonomics

ISSN: 0014-0139 (Print) 1366-5847 (Online) Journal homepage: https://www.tandfonline.com/loi/terg20

# Evaluating input device usability as a function of task difficulty in a tracking task

Michael A. Rupp, Paul Oppold & Daniel S. McConnell

To cite this article: Michael A. Rupp, Paul Oppold & Daniel S. McConnell (2015) Evaluating input device usability as a function of task difficulty in a tracking task, Ergonomics, 58:5, 722-735, DOI: 10.1080/00140139.2014.988755

To link to this article: https://doi.org/10.1080/00140139.2014.988755

Published online: 02 Jan 2015.

Submit your article to this journal

Article views: 606

View related articles

View Crossmark data

Citing articles: 5 View citing articles

Full Terms & Conditions of access and use can be found at
https://www.tandfonline.com/action/journalInformation?journalCode=terg20

---


Ergonomics, 2015
Vol. 58, No. 5, 722–735, http://dx.doi.org/10.1080/00140139.2014.988755

# Evaluating input device usability as a function of task difficulty in a tracking task

Michael A. Rupp<sup>a</sup>*, Paul Oppold<sup>b</sup> and Daniel S. McConnell<sup>a</sup>

<sup>a</sup>Technology and Aging Lab, Department of Psychology, University of Central Florida, Orlando, FL 32816, USA;
<sup>b</sup>Institute for Simulation and Training, University of Central Florida, Orlando, FL, USA

(Received 17 April 2014; accepted 12 November 2014)

Game controllers are emerging as a preferred choice for the manual control of unmanned vehicles, but an understanding of their usability characteristics has yet to emerge. We compared the usability of an Xbox 360 game controller in a dual task situation using MATB II to the traditional joystick and keyboard interface in two experiments. In the first experiment, performance with the game controller was associated with fewer tracking errors. In a second experiment, we trained users on the devices, and found that even after training the game controller was still associated with fewer tracking errors as well as higher usability and lower workload ratings. These results are consistent with the idea that game controllers are highly usable input devices and do not require high mental workload to operate, thus making them suitable for complex control tasks.

**Practitioner Summary:** Game controllers are being used more often for non-gaming purposes include teleoperation of unmanned vehicles. This research investigates the utility of such devices for complex tasks, especially following extensive practice. The game controller was associated with lower workload and fewer errors, indicating its suitability for complex control tasks.

**Keywords:** input devices; game controllers; compensatory tracking; joysticks; human–computer interaction

# 1. Introduction

Remotely operated vehicles have become a standard tool in many domains, with unmanned ground (UGV) and aerial (UAV) vehicles being deployed in the field for military and surveillance use, in search and rescue operations and in scientific operations such as the Mars Rover (Department of Defense 2009; Fong and Thorpe 2001; Billings and Durlach 2008; Durlach, Neumann, and Billings 2008). Small and portable UGVs are being used for reconnaissance and surveillance by dismounted soldiers during field operations, and similar UAVs have been proposed and tested for SWAT for intelligence gathering and reconnaissance, as well as for use in floods, riots and event traffic (Jones et al. 2002). These unmanned aerial platforms cost less, are easier to maintain, require less training for operators and are more mobile than UGVs (Walker, Miller, and Ling 2013).

Furthermore, unmanned vehicles (UVs) are being purchased off the shelf without standardised interface and control systems (Sterling and Perala 2007; Walker, Miller, and Ling 2013). This poses a problem for operators when faced with a wide variety of input devices used for interaction with the unmanned system interface, as the usability of these devices and interfaces have not been verified (Walker, Miller, and Ling 2013). This opens the door to poor design, which can affect performance, increase cognitive workload and increase errors that may lead to the loss of a vehicle (Hancock et al. 2007; Mouloua, Gilson, and Hancock 2003).

## 1.1 Controls for UVs

In most UV systems, teleoperation is achieved with interfaces designed originally for desktop computers, then later adapted to fieldwork with laptop computers (Walker, Miller, and Ling 2013). These systems originally employed joysticks, keyboard and mouse, or proprietary task-specific devices (Axe and Olexa 2008; Billings and Durlach 2008; Durlach, Neumann, and Billings 2008; Rackliffe 2005; Shively, Brasil, and Flaherty 2007). These handheld units are tethered to the user, and carried around the neck or in a backpack, creating a complicated interface for soldiers to use (Walker, Miller, and Ling 2013). Recently, investigators have become interested in finding more intuitive interface devices to replace these bulky systems (Pettitt, Carstens, and Redden 2012; Pettitt et al. 2010).

The novelty of this technology aside, the human operator of remote systems is a critical component and must be equipped with usable controls (Fong and Thorpe 2001; Mouloua, Gilson, and Hancock 2003). An input device should be

*Corresponding author. Email: mrupp@knights.ucf.edu

© 2014 Taylor & Francis

---


Ergonomics                                                         723

evaluated for the characteristics of size and scale, input speed, training time, cognitive workload, impact on physical workload, transfer of training to other, similar systems, minimisation of information overload and overall ease of use (Pettitt, Redden, and Carstens 2008; Pettitt, Carstens, and Redden 2012). With regard to military applications, the device should be small enough to carry, but large enough to be used with gloves. Furthermore, there must be sufficient space between buttons to prevent accidental activation of nearby controls (Pettitt, Carstens, and Redden 2012; Pettitt, Redden, and Carstens 2008). The space on a small controller is limited, and should be able to accommodate two joysticks, used for navigation and camera operation respectively, a sufficient number of buttons and switches for the task, and with either a video screen on the controller or on an attached platform (Pettitt, Redden, and Carstens 2008).

## 1.2 Gamepad controls for UV systems

UAV and UGV systems that have previously relied on standard joysticks or proprietary input devices are more frequently using commercial gamepad controllers (e.g. Microsoft Xbox, Sony PlayStation, etc.) (Axe and Olexa 2008; Walker, Miller, and Ling 2013). Game controllers meet several of the usability criteria listed here. For example, they are smaller, more portable, adaptable to varying tasks, familiar to many operators and are ergonomically designed to be efficient, effective and have high user satisfaction (Axe and Olexa 2008; Pettitt, Redden, and Carstens 2008; Pettitt, Carstens, and Redden 2012). They also do not require a flat surface in order to be used, and do not require as much visual monitoring during operation as other controllers, especially touch screen or mouse-based controls (Billings and Durlach 2008; Pettitt, Carstens, and Redden 2012). Game controllers also provide two joysticks that users can operate separately for navigation, camera control and an array of buttons and triggers, which users can program to perform a variety of operation-specific functions. The joysticks are thumb-operated joysticks and can be set to varying sensitivities to meet operator preferences, although the degree to which the thumb can be used as a precise effector, compared to other digits, has not been evaluated.

In one study (Pettitt et al. 2010), soldiers with prior experience with the Microsoft Xbox 360 controller reported it to be familiar, easy to use and easy to learn when used for a novel telerobotics task. The task required that operators performed steering tasks, obstacle avoidance, sensor head manipulation, target identification, moving target tracking and the control of tread-based flippers to clear low walls, obstacles and stairs (Pettitt et al. 2010; Pettitt, Carstens, and Redden 2012). In another study (Pettitt et al. 2011), the Xbox 360 controller resulted in lower course completion times, lower errors and lower reported workload compared with a virtual joystick running on an Android device. Users also gave it high preference ratings for size, weight, shape, comfort of use, control layout and responsiveness.

In studies of simulated UAV control, game controllers have been associated with faster mission completion times and more target detections during reconnaissance, along with better usability ratings compared with the computer mouse (Durlach, Neumann, and Billings 2008). In later studies incorporating more task training, the faster mission completion times were replicated, although the target detection rates were not (Billings and Durlach 2008, 2010).

Many soldiers operating these systems are young and have extensive prior exposure and experience with game controllers, which could be used to reduce training time and increase performance with UAV and UGV systems (Shively, Brasil, and Flaherty 2007; Pettitt, Carstens, and Redden 2012). Prior familiarity with game controllers may account for some reports of reduced workload when using game controllers of (e.g. Shively, Brasil, and Flaherty 2007). Experienced users of game controllers will have memorised the control layout and will need fewer glances to the device as a reminder of where controls are located. Experienced users should also experience less working memory demands than less experienced users and be expected to report lower mental workload. However, the workload associated with the use of these devices has not been analysed in detail in the literature, and other factors such as physical effort or frustration with the other devices being compared cannot be ruled out.

However, not all studies have reported workload differences between devices, and have attributed differences in performance to the characteristics of the devices themselves, rather than familiarity with them. For example, the game controller is equipped with joysticks which are effective for continuous tasks such as steering and camera operation, while a keyboard, touch screen or a mouse used as a point-and-click device, afford only discrete inputs which are less effective for such tasks (Billings and Durlach 2008, 2010). The goal of the current set of studies is to evaluate further the issues of controller design, familiarity and workload on performance.

## 1.3 Limitations of game controllers

Despite the accumulation of evidence suggesting that game controllers may be the preferred input device for UV control, there are some drawbacks to their use. For example, game controllers typically require two hands to operate, which may make performance of extraneous tasks more difficult (Pettitt, Redden, and Carstens 2008). Moreover, gamepads have not been shown to be consistently preferable in tracking and pointing tasks. Specifically, two studies using a first-person shooter
---


724                M.A. Rupp et al.

video game task found that either gamepads elicited poorer performance (Isokoski and Martin 2007) or no performance differences (Lenz, Chaparro, and Chaparro 2008) compared with other devices such as a mouse or joystick. Another study using a pursuit-tracking task (Klochek and MacKenzie 2006) found that the Xbox controller was worse than a standard mouse using several metrics of performance. Finally, in a Fitts' type discrete pointing task (Fitts and Peterson 1964), researchers compared the performance between a Wii classic controller with a thumb-operated joystick, a Wiimote and a mouse (Natapov, Castellucci, and MacKenzie 2009). Compared with the mouse, both game controllers had higher error rates and movement times, along with poorer ratings of usability.

Nevertheless, game controllers are being used in the field (Axe and Olexa 2008), and this reality mandates further study of the workload and performance issues of game controllers in complex human–system interface tasks. While it might be the case that game controllers do not produce superior performance in an isolated tracking task in the laboratory setting (i.e. Isokoski and Martin 2007; Lenz, Chaparro, and Chaparro 2008), they may be associated with improved performance when the tracking task is combined with multiple secondary tasks, owing to the reduced workload frequently associated with the devices. The multi-attribute task battery (MATB; Comstock and Arnegard 1992; Santiago-Espada et al. 2011) provides an appropriate test bed for this hypothesis, at least within the context of aircraft control.

## 2. Experiment 1

In Experiment 1, we compared the traditional MATB controls consisting of a joystick and keyboard combination to an Xbox 360 game controller programmed to perform tasks in the MATB environment. Using a 2 × 2 independent groups factorial design, we paired the controller manipulation with two levels of task difficulty. This latter manipulation was designed to elicit differing levels of user workload. In the easy condition, users performed a compensatory tracking task. In the difficult condition, additional system monitoring tasks were placed under operator control, so that the user had to perform these functions while simultaneously engaged in the tracking task.

### 2.1 Hypotheses

Based on the literature, we expect differences in workload to account for differences in performance between the controllers. In the easy task with minimal workload demands, we expect minimal differences in performance between the controllers. However, in the difficult condition with greater workload demands, we hypothesise that the game controller will be associated with lower reported mental workload, and consequently fewer tracking errors and higher usability ratings compared with the joystick and keyboard combination. Thus, we are predicting an interaction between controller type and task difficulty. Consistent with previous findings (e.g. Axe and Olexa 2008), we also expect that previous experience with Xbox controllers will be correlated with the various metrics amongst those assigned to use this device in the study, but that differences between the devices will not be solely explained by these correlations.

### 2.2 Participants

We recruited 36 right-handed participants (20 female and 15 male) between the age of 18 and 22 years with normal colour vision and visual acuity from a large university in the southern USA to participate in this study. Participants also reported no other sensory or motor impairments. All received partial or extra course credit in exchange for participation. Overall participants used keyboards (*M*<sub>hrs/wk</sub> = 4.66, SD = 0.54) with more frequency than Xbox controllers (*M*<sub>hrs/wk</sub> = 3.51, SD = 1.34) or joysticks (*M*<sub>hrs/wk</sub> = 2.43, SD = 0.98).

### 2.3 Materials

Prior to participation, participants completed a demographics (e.g. age, sex) and gaming history questionnaire, asking about hours per week of using Xbox, joysticks and keyboards.

#### 2.3.1 Multi-attribute task battery

The MATB is a complex tasking environment developed by NASA as a computer-based simulation platform to evaluate flight crew performance and workload (Natapov, Castellucci, and MacKenzie 2011; Santiago-Espada et al. 2011). We used the newest release, MATB-II (hereafter referred to simply as MATB), in the current studies. The program presents the user with several tasks to create a high workload environment including system monitoring, compensatory tracking and resource management. All tasks are displayed in a single window. We used the default display configuration, with the system monitoring task displayed in the top left corner of the window, and the tracking task in the top right corner. The resource
---


Ergonomics                                                            725

management task was displayed at the bottom of the window, just below the tracking task (see Santiago-Espada et al. 2011 for additional details and images). The compensatory tracking task simulates control of manual flight. A circular reticle was displayed over large crosshairs, with a square at the centre. The goal of the task is to keep the reticle within the square while the software simulates drift in the reticle. The 2D (x, y) position of the reticle was sampled by the software every 5 s and saved as a measure of tracking error. The system-monitoring task simulates the demands of monitoring gauges. In this task, participants have to monitor for two signals, both the absence of a green light and the presence of a red light. When a signal is detected, participants have to press one of the two buttons to restore the lights to the desired state (one button turns the green light back on and another turns the red light off). The resource management task simulates a fuel tank and pump system. The user can turn multiple pumps on and off to direct fuel flow through the system. The goal of this task is to keep two main fuel tanks at an optimal level while balancing the demands of variable fuel flow of the pumps and errors that may arise. When errors arise, users must reroute fuel along a different pathway. The default fuel flow rates were used and each task provided standard visual feedback to the participants during each task. The MATB software has been used in many research studies in the human–computer interaction literature (Comstock and Arnegard 1992; National Aeronautics and Space Administration 2011). For example, Parasuraman, Mouloua, and Molloy (1996) used MATB to study the effect of automation complacency, Bliss and Dunn (2000) used MATB to study the effects of alarm workload, and more recently it has been used in studies of automation trust (e.g. Xu et al. 2014). We used MATB to present the experimental tasks on a PC running Windows 7 on a 43.2 cm (17 in.) LCD display with a resolution of 1280 × 1024 px and a vertical refresh rate of 60 Hz.

Participants used one of two input devices to perform the MATB tasks. Replicating the traditional MATB interface, one device was a joystick and keyboard combination, specifically a Microsoft Sidewinder II joystick paired with a Dell standard 110-key keyboard. In this condition, the default MATB button mapping for the keyboard was used. Participants used the F5 and F6 buttons for the system-monitoring task, and the number keys, 1–8, for the resource management task, while the joystick controlled the crosshairs in the tracking task. Consistent with traditional flight control-display mappings and as is standard for the MATB task, north on the joystick moved the crosshairs down.

The second device was a wired Xbox 360 game controller programmed for use of the left thumbstick for control of the crosshairs in the tracking task. The thumbstick was set to be opposite of the joystick, (i.e. north on the thumbstick moved the crosshairs up) which was consistent with default controller mappings. During pilot testing, a heuristic analysis was performed to assign the game controller buttons to the other tasks (Figure 1). The left and right arrow buttons were mapped to the F5 and F6 keys, respectively, for control of the system-monitoring task. For the resource management task, the buttons A, X, Y and B were mapped to the number keys 1–4, respectively, and the left and right shoulder buttons were mapped to the number keys 5 and 6, respectively, and the left and right trigger buttons were mapped to the number keys 8 and 7, respectively. This mapping was selected to maintain spatial compatibility between the controls and the actions in the fuel pump system (e.g. pump 7 moves fuel to the right; hence the right trigger was used to perform this action). The Pinnacle

<table>
<tr>
<td colspan="2" style="text-align: center;">
<strong>Tracking</strong><br>
<br>
[Xbox 360 Controller Image with labeled buttons]<br>
<br>
Button mappings:<br>
2 - Top face button<br>
3 - Right face button<br>
4 - Bottom face button<br>
1 - Left face button<br>
F5 - Left directional pad<br>
F6 - Right directional pad<br>
8 - Left trigger<br>
7 - Right trigger<br>
5 - Left shoulder button<br>
6 - Right shoulder button
</td>
</tr>
</table>

**Figure 1.** The Xbox controller layout used in Experiments 1 and 2. The controller buttons were mapped to the keyboard function and number keys as shown.
---


726                                             M.A. Rupp et al.

Game Profiler application (PowerUp Software, LLC) was used to map the controller buttons as described, and to control for sensitivity between the Sidewinder and Xbox control sticks.

## 2.3.2 NASA Task Load Index

We used the computerised version of the NASA Task Load Index (NASA-TLX) (Hart and Staveland 1988) to obtain subjective workload ratings regarding the task. The NASA-TLX is a multi-dimensional rating scale that generates an overall workload rating based on six subscales (mental workload, physical workload, temporal workload, subjective rating of performance, effort and frustration). This measure is completed in two parts, during the first part users rate each individual subscale, and during part two they complete pairwise comparisons to determine which aspect of workload is dominated by the task (Hart and Staveland 1988).

## 2.3.3 System usability scale

The system usability scale (SUS; Brooke 1996) was used as a measure of the usability of the input devices. Participants rated their level of agreement on a five-point Likert-type scale. The items were modified to include the word interface in place of system, emphasising that the participants were rating the usability of the input device, not the MATB task(s). Otherwise, we collected and analysed the data according to the default instructions.

## 2.4 Procedure

At the beginning of the session, following provision of consent, participants completed the demographics survey, and we gave each participant a screening for visual acuity and colour deficiencies. We then randomly assigned participants into one of four conditions, as derived from the 2 × 2 factorial combination of the two input devices and two levels of task difficulty. The easy task involved tracking only, during which participants assigned to the joystick/keyboard combination would operate only the joystick with their right hand, and those assigned to the Xbox controller only used the left thumbstick, to perform the tracking task while they held onto the device with the both hands. Otherwise, the system monitoring and resource management tasks were automated and controlled by the computer. In the difficult condition, depending on condition, participants would use either the keyboard or extra buttons on the Xbox controller to perform the system monitoring and resource management tasks. In this condition, those using the Xbox controller held the device in both hands directly in front of their body and used the left thumb stick for the tracking task and used both hands to press the buttons for the secondary tasks. Participants in the joystick and keyboard condition used the joystick with the left hand for the tracking condition and participants used their right hand to complete the secondary tasks using the keyboard concurrently. In the difficult condition, the systems were programmed to exhibit a randomised failure event rate of approximately two events per minute for both the system monitoring and resource management tasks.

Following instruction, participants completed a pre-task NASA-TLX, and we gave each participant a 5-min practice session on the task before they attempted the 10-min test session. Following the experimental task, participants completed the NASA-TLX and SUS survey as post-task measures. The duration of the entire session was approximately 30 min.

## 2.5 Results

Tracking error was computed from the crosshair locations as sampled by the MATB software, and was defined as the root mean square deviation from target centre (RMSD-C). For all analyses, unless otherwise stated, an alpha level of 0.05 was used, Table 1 contains the means, standard deviations and intercorrelations among the study variables. Prior to analyses, all variables were reviewed for outliers (± 3 SD from the mean), assumptions of normality (skewness and kurtosis) and interrelationships. We did not find any significant deviations from the assumptions of normality and we found moderate correlations between the dependent variables. One participant who was in the joystick and keyboard easy condition was removed from the study due to having an RMSD-C of over four standard deviations above the mean, leaving a total of 35 participants in the final analyses. We also calculated Bayesian posterior probabilities of the alternative hypothesis being true given the data [ p BIC(H<sub>1</sub>|D)] using the techniques outlined by Masson (2011). A [ p BIC(H<sub>1</sub>|D) < 0.05] indicates support for the null hypothesis, whereas a [ p BIC(H<sub>1</sub>|D) > 0.05] indicates support for the alternative hypothesis given the data.

As reported in Table 1, experience with using the Xbox controller correlated negatively with tracking errors when using this controller, [r = −0.41, p < 0.05] and SUS ratings for the device [r = 0.48, p < 0.01]. The correlation between Xbox controller use and reported workload when using the device was modest and not significant [r = −0.21, p > 0.05]. Few users reported experience with the joystick and correlations involving this measure could not be computed.
---


Ergonomics                                                                            727

**Table 1.** Mean, standard deviations and variable correlations for study 1.

<table>
<thead>
<tr>
<th></th>
<th>Variable</th>
<th>M</th>
<th>SD</th>
<th>1</th>
<th>2</th>
<th>3</th>
<th>4</th>
<th>5</th>
<th>6</th>
<th>7</th>
<th>8</th>
<th>9</th>
</tr>
</thead>
<tbody>
<tr>
<td>1</td>
<td>Sex</td>
<td>0.43</td>
<td>0.5</td>
<td>1</td>
<td></td>
<td></td>
<td></td>
<td></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr>
<td>2</td>
<td>Age (years)</td>
<td>19.10</td>
<td>1.20</td>
<td>0.18</td>
<td>1</td>
<td></td>
<td></td>
<td></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr>
<td>3</td>
<td>Joystick (h)</td>
<td>0.63</td>
<td>3.40</td>
<td>0.22</td>
<td>−0.01</td>
<td>1</td>
<td></td>
<td></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr>
<td>4</td>
<td>Xbox (h)</td>
<td>3.47</td>
<td>5.00</td>
<td><strong>0.48</strong></td>
<td>−0.01</td>
<td>–</td>
<td>1</td>
<td></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr>
<td>5</td>
<td>AVG (h)</td>
<td>3.77</td>
<td>5.45</td>
<td><strong>0.65</strong></td>
<td>0.04</td>
<td>–</td>
<td><strong>0.94<sup>a</sup></strong></td>
<td>1</td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr>
<td>6</td>
<td>SUS</td>
<td>74.14</td>
<td>19.75</td>
<td>0.18</td>
<td>0.15</td>
<td>–</td>
<td><strong>0.48<sup>a</sup></strong></td>
<td>−0.06</td>
<td>1</td>
<td></td>
<td></td>
<td></td>
</tr>
<tr>
<td>7</td>
<td>Tracking (RMSD-C)</td>
<td>31.19</td>
<td>12.08</td>
<td>−0.29</td>
<td>0.11</td>
<td>–</td>
<td><strong>−0.41<sup>a</sup></strong></td>
<td>−0.33</td>
<td>−0.32</td>
<td>1</td>
<td></td>
<td></td>
</tr>
<tr>
<td>8</td>
<td>Workload Pre-task (TLX)</td>
<td>29.84</td>
<td>20.81</td>
<td>−0.19</td>
<td>−0.29</td>
<td>–</td>
<td>0.20<sup>a</sup></td>
<td>−0.22</td>
<td>−0.19</td>
<td>0.12</td>
<td>1</td>
<td></td>
</tr>
<tr>
<td>9</td>
<td>Workload Post-task (TLX)</td>
<td>610.40</td>
<td>19.90</td>
<td><strong>−0.38</strong></td>
<td><strong>−0.36</strong></td>
<td>–</td>
<td>−0.21<sup>a</sup></td>
<td>−0.14</td>
<td><strong>−0.44</strong></td>
<td>0.20</td>
<td><strong>0.53</strong></td>
<td>1</td>
</tr>
</tbody>
</table>

Note: Correlations greater than ±0.32 are significant at p < 0.05 (two-tailed) and correlations ±0.44 are significant at p < 0.01 (two-tailed). Correlations significant at p < .05 are in bold. Sex: females were coded as 0 and males were coded as 1.
<sup>a</sup> This correlation only contains participants in the Xbox condition. In the joystick condition, no one reported having any joystick hours so we did not report those correlations.

To reduce the likeliness of type I error across multiple dependent measures, we conducted a 2 × 2 independent groups MANOVA to evaluate the effects of the input devices and task difficulty on the three dependent variables of RMSD-C, NASA-TLX and SUS scores. Before we conducted the analysis, pre-task NASA-TLX scores, extraversion and device-specific experience were evaluated as possible covariates. However, none of these variables met inclusion criteria due to lack of homogeneity of regression slopes across all variable interactions and low intercorrelations among the study variables. The results of the analysis after adjustment for the covariates did not differ from the results without the covariates. For simplicity, we thus did not include the covariates in the analyses. We report the means, standard deviations and intercorrelations among the relevant study variables in Table 1.

Using Wilks' lambda criterion, the independent variables had statistically significant effects on the composite dependent variable [F(3, 29) = 7.59, p < 0.001, partial η<sup>2</sup> = 0.44, p BIC(H<sub>1</sub>|D) = 0.99 for task difficulty (λ = 0.56)], [F(3, 29) = 14.06, p < 0.001, partial η<sup>2</sup> = 0.60, p BIC(H<sub>1</sub>|D) = 0.99 for controller (λ = 0.41)]. However, the interaction was not significant [(λ = 0.88), p = 0.322, partial η<sup>2</sup> = 0.11, p BIC(H<sub>1</sub>|D) = 0.037]. Because the multivariate tests were significant, separate ANOVAs were then conducted on each dependent measure.

## 2.5.1 Tracking error

In terms of tracking error, the RMSD-C was higher in the difficult task (M = 36.30, SD = 13.70) compared with the easy task (M = 25.78, SD = 7.14) [F(1, 31) = 20.48, p < 0.001, partial η<sup>2</sup> = 0.40, p BIC(H<sub>1</sub>|D) = 0.99]. The nature of the input device also had an effect on tracking error, with a higher RMSD-C for the joystick (M = 38.87, SD = 11.71) compared with the Xbox controller (M = 23.06, SD = 5.32) [F(1, 31) = 44.56, p < 0.001, partial η<sup>2</sup> = 0.59, p BIC(H<sub>1</sub>|D) = 0.99]. Although a pattern was apparent (Figure 2(a)), suggesting that the difference between the high and low difficulty tasks was more pronounced for the joystick/keyboard condition than in the Xbox controller condition, evidence for this interaction was not compelling [F(1, 31) = 3.43, p = 0.074, partial η<sup>2</sup> = 0.10, p BIC(H<sub>1</sub>|D) = 0.52].

<table>
<thead>
<tr>
<th>Condition</th>
<th>Experiment 1</th>
<th>Experiment 2 Pre-training</th>
<th>Experiment 2 Post-training</th>
</tr>
</thead>
<tbody>
<tr>
<td>Xbox Controller - Easy</td>
<td>~22</td>
<td>~25</td>
<td>~23</td>
</tr>
<tr>
<td>Xbox Controller - Difficult</td>
<td>~30</td>
<td>~28</td>
<td>~25</td>
</tr>
<tr>
<td>Joystick/Keyboard - Easy</td>
<td>~35</td>
<td>~45</td>
<td>~35</td>
</tr>
<tr>
<td>Joystick/Keyboard - Difficult</td>
<td>~48</td>
<td>~55</td>
<td>~70</td>
</tr>
</tbody>
</table>

**Figure 2.** Tracking error (RMSD-C) in (a) Experiment 1, (b) Experiment 2 Day 1 (pre-training), (c) Experiment 2 post-training, as a function of task difficulty and input device. Error bars indicate SE.
---


728                                            M.A. Rupp et al.

## 2.5.2 Workload

Post-task workload, as measured by the NASA-TLX, was only slightly higher in the difficult condition (M = 67.30, SD = 15.40) compared with the easy condition (M = 55.14, SD = 22.56) [F(1, 31) = 3.43, p = 0.074, partial η<sup>2</sup> = 0.10, p BIC(H<sub>1</sub>|D) = 0.52]. There was also no effect of input device on workload [F(1, 31) = 0.429 p = 0.52, η<sup>2</sup> = 0.014, p BIC (H<sub>1</sub>|D) = 0.18] and no interaction [F(1, 31) = 0.035 p = 0.85, η<sup>2</sup> = 0.001, p BIC(H<sub>1</sub>|D) = 0.14] between task difficulty and input device on this measure (Figure 3(a)).

## 2.5.3 Usability

Usability, as measured by the SUS, was not affected by task difficulty [F(1, 31) = 1.07 p = 0.31, η<sup>2</sup> = 0.033, p BIC (H<sub>1</sub>|D) = 0.23], nor by input device [F(1, 31) = 2.27 p = 0.15, η<sup>2</sup> = 0.067, p BIC(H<sub>1</sub>|D) = 0.36]. These two factors also did not interact (Figure 4(a)) to influence usability [F(1, 31) = 0.135 p = 0.72, η<sup>2</sup> = 0.004, p BIC(H<sub>1</sub>|D) = 0.15].

## 2.6 Discussion

We predicted that, compared with the joystick, use of the Xbox controller would be associated with fewer tracking errors and higher usability scores only in the difficult condition, and that these effects would be explained in terms of differences in workload. While there were patterns in the tracking and workload data consistent with the prediction, the statistical evidence for a two-way interaction between controller type and task difficulty was not compelling. The evidence instead suggests that tracking error was lower for the Xbox controller across both levels of difficulty. Given this, and that there

<table>
<thead>
<tr>
<th>Condition</th>
<th>Xbox Controller Easy</th>
<th>Xbox Controller Difficult</th>
<th>Joystick/Keyboard Easy</th>
<th>Joystick/Keyboard Difficult</th>
</tr>
</thead>
<tbody>
<tr>
<td>Experiment 1</td>
<td>~55</td>
<td>~65</td>
<td>~60</td>
<td>~70</td>
</tr>
<tr>
<td>Experiment 2 Pre-training</td>
<td>~50</td>
<td>~60</td>
<td>~50</td>
<td>~75</td>
</tr>
<tr>
<td>Experiment 2 Post-training</td>
<td>~25</td>
<td>~45</td>
<td>~35</td>
<td>~65</td>
</tr>
</tbody>
</table>

**Figure 3.** Subjective workload (NASA-TLX) in (a) Experiment 1, (b) Experiment 2 Day 1 (pre-training), (c) Experiment 2 post-training, as a function of task difficulty and input device. Error bars indicate SE.

<table>
<thead>
<tr>
<th>Condition</th>
<th>Xbox Controller Easy</th>
<th>Xbox Controller Difficult</th>
<th>Joystick/Keyboard Easy</th>
<th>Joystick/Keyboard Difficult</th>
</tr>
</thead>
<tbody>
<tr>
<td>Experiment 1</td>
<td>~85</td>
<td>~75</td>
<td>~75</td>
<td>~70</td>
</tr>
<tr>
<td>Experiment 2 Post-training</td>
<td>~95</td>
<td>~85</td>
<td>~70</td>
<td>~65</td>
</tr>
</tbody>
</table>

**Figure 4.** Usability ratings (SUS) in (a) Experiment 1, (b) Experiment 2 post-training, as a function of task difficulty and input device. Error bars indicate SE.
---


Ergonomics                                            729

were no differences in reported workload between the devices, and that the correlation between Xbox controller experience and reported workload when using the device was modest and not significant, then the results as a whole do not support the hypothesised idea that workload would account for differences in tracking performance between the devices.

We had previously considered that familiarity affects performance with the device by reducing mental workload in the form of reduced memory demands in regard to remembering the layout of controls on the device. The current results are not consistent with this idea. Nevertheless, experience with game controllers was a factor that affected performance, as evidenced by the correlation between this measure and both tracking error and SUS ratings. The familiarity of game controllers, and reported unfamiliarity with joysticks, may thus account for the main effect of device on tracking error. In fact, one might predict that if experience was the primary explanation for the performance differences, then it would lead to better performance across all tasks, and thus would account for the observed main effect and lack of a two-way interaction.

The nature of the relationship between device experience and performance has thus not been explained fully by these results, and the role of device-specific characteristics remains unclear. The importance of experience is further compounded by the overall lack of reported joystick use amongst the participants. With a goal of dissociating familiarity effects from particularities of device design, and thus to elucidate the effects of the latter variable, we employ a practice regimen in Experiment 2 to normalise user familiarity across devices. As a result, remaining differences between them can be understood in terms of device-specific characteristics.

## 3. Experiment 2

Participants in Experiment 1 reported more experience using game controllers than joysticks, and furthermore, higher levels of controller experience were associated with fewer tracking errors. Thus, we were left to conclude that device familiarity best accounts for the findings, and not any device-specific characteristic that affected performance, whether related to workload or any other factor. Any such factors, if they are to be understood, must be tested under conditions that minimise familiarity effects that may otherwise mask them. To achieve this, we introduced a practice regimen designed to minimise differences in experience between the devices, at least for the task at hand. In Experiment 2, we replicate the design of the first experiment, using a 2 × 2 independent groups factorial design with control type and task difficulty as independent variables. The key difference is that participants will undergo the practice regimen across several days prior to testing.

### 3.1 Hypotheses

The set-up of Experiment 2 enables us to test between two competing predictions regarding experience and device characteristics and their effects on performance. If differences in performance are mainly attributable to experience and familiarity with the devices, then as the practice regimen serves to equate experience levels, performance differences between the devices would be expected to diminish, consistent with the results of Lenz, Chaparro, and Chaparro (2008). To the extent that there are any remaining differences in performance between devices, or especially if differences between the devices become magnified, then such an effect would be attributable to some characteristic of the device.

At the beginning of the sessions, on the first day of the experiment, the testing conditions were essentially an exact replication of Experiment 1, and analysis of this pre-training session should replicate those findings. After the practice regimen is finished, performance was measured during a post-training session, and the results enabled a test between the predictions of the experience hypothesis versus the device characteristic hypothesis.

### 3.2 Participants

Fifty-three right-handed participants (30 female and 23 male) between the age of 18 and 33 years with normal colour vision and visual acuity (both near and far) were recruited from a large university in the southern USA to participate in Experiment 2. They received partial or extra course credit in exchange for participation. All participants also reported no sensory or motor impairments. Overall participants used keyboards (M<sub>hrs/wk</sub> = 5.43, SD = 0.62) more frequently than Xbox controllers (M<sub>hrs/wk</sub> = 7.94, SD = 1.68) or joysticks (M<sub>hrs/wk</sub> = 1.17, SD = 0.59).

### 3.3 Materials

The tasks, measures and devices used were identical to those in Experiment 1, except for the introduction of a subjective debriefing interview in which participants were asked to describe their experience with the interface following the post-training session.
---


730                                                        M.A. Rupp et al.

## 3.4 Procedure

Prior to the start of Experiment 2, a pilot study was conducted to determine the training schedule. During the pilot study, participants completed four 10-min sessions during a 1-hour sitting each day for four consecutive days. Visual inspection of tracking error data revealed that performance improved across sessions but did so differently as a function of task difficulty. Regardless of input device, participants in the easy task reached a levelling off of performance on the third day, while those in the difficult task achieved this levelling off on the fourth day. On this basis, we decided that those in the easy task condition would practise the device for three consecutive days at the same time each day, while participants in the difficult task condition were given four days of practice.

As in Experiment 1, the MATB task took 10 min to complete, but the total session duration varied depending on the number of sessions completed. On Day 1 of the study, participants were randomly assigned to one of the four possible device and task conditions. They then completed the demographics questionnaire, a pre-task NASA-TLX, and a single session of the MATB task corresponding to the condition to which they were assigned. Thus, in addition to being the beginning of the training schedule, Day 1 also served as a replication of Experiment 1. Training consisted of simple practice on the task. No feedback or knowledge of results was provided to participants.

Training continued on the second day of the experiment. Participants in the easy task condition experienced four sessions on Day 2 of the experiment and two sessions on Day 3. Those in the difficult task condition underwent four sessions on Day 2, four sessions on Day 3 and two sessions on Day 4 of the experiment. Five-minute breaks were provided between each MATB session. In total, those in the easy condition were given 7 sessions before post-training testing, whereas those in the difficult condition were given 11 sessions prior to the post-training session. A separate post-testing session was conducted on the day following the participant's final training session. Even though participants received more practice in the difficult task condition than did those in the easy task condition, the results of the pilot study gave us no reason to expect any benefit of longer practice on the easy task. Thus, fair comparisons can be drawn from the post-training session on the assumption that performance in each condition had levelled off. During post-training testing, participants were given two sessions of the MATB task each followed by a NASA-TLX rating; after the second MATB session, participants were asked to complete the SUS.

## 3.5 Results

The dependent variables of RMSD-C and NASA-TLX were recorded for the pre-training session and the post-training session. The SUS was administered only after the post-training session. Consistent with Experiment 1, Xbox experience correlated with Day 1 tracking errors with the device [r = −0.33, p < 0.05] and did not correlate with reported workload with the device [r = −0.09, p > 0.05], as shown in Table 2. A sufficient number of participants reported joystick experience so that correlations could be computed between this measure and the dependent variables. Joystick experience correlated neither with tracking error when using joysticks [r = −0.05, p > 0.05] nor workload associated with them [r = −0.06, p > 0.05].

Next, we conducted a 2 × 2 independent groups MANOVA on the combined dependent variables as measured during pre-training. Prior to all analyses, we screened the data for assumptions following the same procedure as Experiment 1.

<table>
<thead>
<tr>
<th>Variable</th>
<th>M</th>
<th>SD</th>
<th>1</th>
<th>2</th>
<th>3</th>
<th>4</th>
<th>5</th>
<th>6</th>
<th>7</th>
<th>8</th>
<th>9</th>
<th>10</th>
<th>11</th>
</tr>
</thead>
<tbody>
<tr>
<td>1 Sex</td>
<td>0.57</td>
<td>0.5</td>
<td>1</td>
<td></td>
<td></td>
<td></td>
<td></td>
<td></td>
<td></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr>
<td>2 Age (years)</td>
<td>20.11</td>
<td>30.14</td>
<td>0.02</td>
<td>1</td>
<td></td>
<td></td>
<td></td>
<td></td>
<td></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr>
<td>3 Joystick (h)</td>
<td>1.17</td>
<td>4.30</td>
<td>0.22</td>
<td><strong>0.29</strong></td>
<td>1</td>
<td></td>
<td></td>
<td></td>
<td></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr>
<td>4 Xbox (h)</td>
<td>7.94</td>
<td>12.30</td>
<td>0.10</td>
<td>−0.12</td>
<td>−0.17<sup>a</sup></td>
<td>1</td>
<td></td>
<td></td>
<td></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr>
<td>5 AVG (h)</td>
<td>9.25</td>
<td>14.64</td>
<td><strong>0.29</strong></td>
<td>−0.14</td>
<td>−0.08<sup>a</sup></td>
<td><strong>0.50<sup>†</sup></strong></td>
<td>1</td>
<td></td>
<td></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr>
<td>6 Tracking (Day 1; RMSD-C)</td>
<td>33.58</td>
<td>15.33</td>
<td><strong>−0.29</strong></td>
<td>0.001</td>
<td>−0.05<sup>a</sup></td>
<td><strong>−0.33<sup>a</sup></strong></td>
<td>−0.02</td>
<td>1</td>
<td></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr>
<td>7 Workload (Day 1; TLX)</td>
<td>57.25</td>
<td>20.08</td>
<td><strong>−0.43</strong></td>
<td>0.10</td>
<td>−0.06<sup>a</sup></td>
<td>−0.09<sup>a</sup></td>
<td>−0.08</td>
<td><strong>0.37</strong></td>
<td>1</td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr>
<td>8 SUS</td>
<td>78.54</td>
<td>15.03</td>
<td>0.20</td>
<td>0.05</td>
<td>0.12<sup>a</sup></td>
<td>−0.10<sup>a</sup></td>
<td>−0.02</td>
<td><strong>−0.50</strong></td>
<td><strong>−0.25</strong></td>
<td>1</td>
<td></td>
<td></td>
<td></td>
</tr>
<tr>
<td>9 Tracking Post-task (RMSD-C)</td>
<td>34.37</td>
<td>26.14</td>
<td><strong>−0.39</strong></td>
<td>0.24</td>
<td>−0.15<sup>a</sup></td>
<td><strong>−0.33<sup>a</sup></strong></td>
<td>−0.12</td>
<td><strong>0.72</strong></td>
<td><strong>0.35</strong></td>
<td><strong>−0.33</strong></td>
<td>1</td>
<td></td>
<td></td>
</tr>
<tr>
<td>10 Workload Pre-task (TLX)</td>
<td>19.93</td>
<td>17.74</td>
<td>0.20</td>
<td>−0.21</td>
<td>−0.22<sup>a</sup></td>
<td>0.01<sup>a</sup></td>
<td><strong>0.33</strong></td>
<td>−0.05</td>
<td>0.14</td>
<td>−0.01</td>
<td>−0.19</td>
<td>1</td>
<td></td>
</tr>
<tr>
<td>11 Workload Post-task (TLX)</td>
<td>41.70</td>
<td>22.51</td>
<td><strong>−0.31</strong></td>
<td>0.08</td>
<td>−0.25<sup>a</sup></td>
<td>0.11<sup>a</sup></td>
<td>−0.03</td>
<td><strong>0.48</strong></td>
<td><strong>0.53</strong></td>
<td><strong>−0.38</strong></td>
<td><strong>0.50</strong></td>
<td>0.05</td>
<td>1</td>
</tr>
</tbody>
</table>

**Table 2.** Mean, Standard Deviations and variable correlations for study 2.

Note: correlations greater than ±0.28 are significant at p < 0.05 (two-tailed) and correlations ±0.36 are significant at p < 0.01 (two-tailed). Correlations significant at p < .05 are in bold. Sex: females were coded as 0 and males were coded as 1.
<sup>a</sup> This correlation only contains participants in the Xbox condition.
<sup>b</sup> These correlations only contain participants in the joystick condition.
---


Ergonomics                                   731

Box's test was significant, *p* < 0.001, suggesting a violation of the assumption of equality of covariance matrices. Thus, we used the more conservative Pillai's Trace criterion to evaluate the effects in the MANOVA. We found an effect of input device on the composite variable [*F*(2, 48) = 33.45, *p* < 0.001, partial η<sup>2</sup> = 0.58, *p* BIC(*H*<sub>1</sub>|*D*) = 0.99], as well as task difficulty [*F*(2, 48) = 9.63, *p* < 0.001, partial η<sup>2</sup> = 0.29, *p* BIC(*H*<sub>1</sub>|*D*) = 0.99] though there was no interaction between the two factors [*F*(2, 48) = 2.17, *p* = 0.126, partial η<sup>2</sup> = 0.083, *p* BIC(*H*<sub>1</sub>|*D*) = 0.99]. Separate univariate 2 × 2 ANOVAs were next conducted on each dependent variable.

## 3.5.1 Pre-training tracking error

Tracking error was higher in the difficult task condition (*M* = 36.26, SD = 17.88) compared with the easy task (*M* = 30.34, SD = 11.02) [*F*(1, 49) = 7.49, *p* = 0.009, partial η<sup>2</sup> = 0.13, *p* BIC(*H*<sub>1</sub>|*D*) = 0.84]. Manipulation of input device resulted in RMSD-C for the joystick/keyboard combination (*M* = 46.32, SD = 14.84) that was twice as large as the Xbox controller (*M* = 23.80, SD = 5.15) [*F*(1, 49) = 67.43, *p* < 0.001, partial η<sup>2</sup> = 0.58, *p* BIC(*H*<sub>1</sub>|*D*) = 0.99]. There was no interaction effect on tracking error (Figure 2(b)) [*F*(1, 49) = 2.58, *p* = 0.115, partial η<sup>2</sup> = 0.050, *p* BIC(*H*<sub>1</sub>|*D*) = 0.35].

## 3.5.2 Pre-training workload

Workload was higher in the difficult task (*M* = 65.02, SD = 16.02) compared with the easy task (*M* = 47.86, SD = 20.75) [*F*(1, 49) = 14.611, *p* < 0.001, partial η<sup>2</sup> = 0.23, *p* BIC(*H*<sub>1</sub>|*D*) = 0.99]. Workload was also somewhat higher for the joystick/keyboard combination (*M* = 62.71, SD = 21.43) than the Xbox controller (*M* = 53.07, SD = 18.49) [*F*(1, 49) = 4.10, *p* = 0.049, partial η<sup>2</sup> = 0.08, *p* BIC(*H*<sub>1</sub>|*D*) = 0.56]. However, we do not consider there to be strong evidence supporting this effect due to the low effect size and low posterior probability of the alternative hypothesis being true given the data. There was no interaction effect on workload ratings (Figure 3(b)) [*F*(2, 48) = 2.48, *p* = 0.125, partial η<sup>2</sup> = 0.047, *p* BIC(*H*<sub>1</sub>|*D*) = 0.32].

We conducted the pre-training sessions under the same conditions as Experiment 1, and thus expected similar results. Overall, the results were similar (Figures 2(a), (b) and 3(a), (b)), except for the newly reported main effect of input device on workload ratings. However, the size of this effect was small, and Experiment 2 included 18 more participants than Experiment 1, resulting in more statistical power. Furthermore, the Bayesian analysis showing the posterior probability of the alternative hypothesis given the data was only slightly above chance.

## 3.5.3 Training sessions

Next, we analysed performance across the practice sessions. Mean RMSD-C was recorded after each session, and separate linear regressions, for each participant, were conducted on these data. The slopes of these individual regressions of session against RMSD-C were averaged across participants to create average slopes. The effects of practice varied by condition and device (Figure 5). Tracking error, already low for the Xbox controller, declined slightly over sessions in the difficult condition, with a mean slope of −0.05, with a little more improvement shown by those in the easy condition, with a mean slope of −0.23. While tracking error also declined for participants using the joystick in the easy task condition, with a mean slope of −1.10, tracking error slightly increased for those using the joystick in the difficult task condition, with a mean slope of 0.26.

## 3.5.4 Post-training data

Data from the two post-training sessions were averaged together. The correlation between Xbox controller experience and tracking error from these sessions remained the same as found on Day 1 [*r* = −0.33, *p* < 0.05], as did the correlation between Xbox experience and workload [*r* = 0.11, *p* > 0.05]. Experience with this device did not correlate with SUS ratings [*r* = −0.10, *p* > 0.05]. Experience with joysticks did not correlate with tracking errors for those who used joysticks [*r* = −0.15, *p* > 0.05], workload [*r* = −0.25, *p* > 0.05] or SUS ratings [*r* = 0.12, *p* > 0.05].

We performed a 2 × 2 independent groups MANOVA on the combined dependent variables averaged across these two sessions. As in Experiment 1, we evaluated device experience as potential covariates. The results of the analysis after adjustment for the covariates were the same as conducting the analysis without the covariates; thus, we report the results of the analysis without the covariates here. We report the means, standard deviations and intercorrelations among the study variables in Table 2. As mentioned earlier, Box's test was significant (*p* < 0.001), suggesting a violation of the assumption of equality of covariance matrices, so we again used Pillai's trace criteria to evaluate the effects of the MANOVA. We found an effect of input device on the composite variable [*F*(3, 47) = 27.40, *p* < 0.001, partial η<sup>2</sup> = 0.64, *p* BIC
---


732                                    M.A. Rupp et al.

<table>
<thead>
<tr>
<th>Day and Session</th>
<th>Xbox, Low Difficulty</th>
<th>Xbox, High Difficulty</th>
<th>Joystick, Low Difficulty</th>
<th>Joystick, High Difficulty</th>
</tr>
</thead>
<tbody>
<tr>
<td>1</td>
<td>~45</td>
<td>~25</td>
<td>~35</td>
<td>~53</td>
</tr>
<tr>
<td>2a</td>
<td>~42</td>
<td>~26</td>
<td>~35</td>
<td>~53</td>
</tr>
<tr>
<td>2b</td>
<td>~40</td>
<td>~27</td>
<td>~43</td>
<td>~58</td>
</tr>
<tr>
<td>2c</td>
<td>~38</td>
<td>~28</td>
<td>~36</td>
<td>~54</td>
</tr>
<tr>
<td>2d</td>
<td>~36</td>
<td>~28</td>
<td>~36</td>
<td>~54</td>
</tr>
<tr>
<td>3a</td>
<td></td>
<td>~27</td>
<td></td>
<td>~46</td>
</tr>
<tr>
<td>3b</td>
<td></td>
<td>~26</td>
<td></td>
<td>~45</td>
</tr>
<tr>
<td>3c</td>
<td></td>
<td>~27</td>
<td></td>
<td>~50</td>
</tr>
<tr>
<td>3d</td>
<td></td>
<td>~27</td>
<td></td>
<td>~52</td>
</tr>
<tr>
<td>4a</td>
<td>~35</td>
<td>~25</td>
<td>~33</td>
<td>~54</td>
</tr>
<tr>
<td>4b</td>
<td>~33</td>
<td>~25</td>
<td>~32</td>
<td>~57</td>
</tr>
<tr>
<td>5a</td>
<td>~23</td>
<td>~67</td>
<td>~23</td>
<td>~67</td>
</tr>
<tr>
<td>5b</td>
<td>~23</td>
<td>~68</td>
<td>~23</td>
<td>~68</td>
</tr>
</tbody>
</table>

**Figure 5.** Tracking error (RMSD-C) as a function of session. Days are labelled by numbers on the x-axis, with letters indicating the sessions performed on a given day. As explained in the text, participants in the difficult conditions received ten training sessions (indicated by filled symbols in the figure) spread over three days. Participants in the easy conditions received six training sessions spread over 2 days. Two post-training sessions (indicated by open symbols in the figure) were conducted on Day 5 (for those in the difficult condition) or Day 4 (for those in the easy condition). Error bars indicate SE.

(H<sub>1</sub>|D) = 1.00], and an effect of task difficulty [F(3, 47) = 11.00, p < 0.001, partial η<sup>2</sup> = 0.42, p BIC(H<sub>1</sub>|D) = 0.99], and also an interaction between the two factors [F(3, 47) = 3.30, p = 0.029, partial η<sup>2</sup> = 0.17, p BIC(H<sub>1</sub>|D) = 0.72]. Next, we evaluated each dependent variable separately using 2 × 2 independent groups ANOVAs.

### 3.5.5 Post-training tracking errors

In analysis of the tracking errors, Levene's test of the assumption of homogeneity of error variance was significant [F (3, 49) = 46.03, p < 0.001]. A larger variance was observed primarily for the joystick and keyboard condition (difficult task) compared with all other conditions. We adopted a more stringent significance level (α = 0.01) for subsequent analysis of the tracking error data, to avoid for potential type I errors. RMSD-C was higher in the difficult task (M = 41.53, SD = 33.00) compared to the easy task (M = 25.74, SD = 8.76) [F(1, 49) = 12.63, p = 0.001, partial η<sup>2</sup> = 0.21, p BIC(H<sub>1</sub>|D) = 0.98]. The joystick was associated with higher RMSD-C (M = 50.37, SD = 33.42) than the Xbox controller (M = 22.11, SD = 4.43) [F(1, 49) = 26.80, p < 0.001, partial η<sup>2</sup> = 0.35, p BIC (H<sub>1</sub>|D) = 0.99]. These two factors interacted (Figure 2(c)), producing a more pronounced difference in tracking error between the controllers in the difficult task compared with the easy task [F(1, 49) = 8.62, p = 0.005, partial η<sup>2</sup> = 0.15, p BIC(H<sub>1</sub>|D) = 0.91].

### 3.5.6 Post-training workload

Workload was higher in the difficult condition (M = 51.05, SD = 21.63) than the easy condition (M = 30.40, SD = 18.25) [F(1, 49) = 19.44, p < 0.001, partial η<sup>2</sup> = 0.28, p BIC(H<sub>1</sub>|D) = 0.99]. The joystick/keyboard combination (M = 51.14, SD = 25.46) also accounted for higher workload ratings than the Xbox controller (M = 34.48, SD = 17.09) [F(1, 49) = 11.47, p = 0.001, partial η<sup>2</sup> = 0.19, p BIC(H<sub>1</sub>|D) = 0.97]. The two factors did not interact (Figure 3(c)) on workload ratings [F(1, 49) = 1.73, p = 0.195, partial η<sup>2</sup> = 0.034, p BIC(H<sub>1</sub>|D) = 0.26].
---


Ergonomics                                                                                           733

## 3.5.7 Post-training usability

Overall, the controllers were rated as more usable in the easy condition (M = 82.40, SD = 13.74) than the difficult condition (M = 75.35, SD = 15.52) [F(1, 49) = 6.10, p = 0.017, partial η<sup>2</sup> = 0.11, p BIC(H<sub>1</sub>|D) = 0.75]. Furthermore, the Xbox controller was rated as more usable (M = 87.00, SD = 11.11) than the joystick/keyboard combination (M = 67.50, SD = 12.08) [F(1, 49) = 44.68 p < 0.001, partial η<sup>2</sup> = 0.48, p BIC(H<sub>1</sub>|D) = 0.99]. These two factors did not interact (Figure 3(b)) to influence usability [F(1, 49) = 1.72 p = 0.196, partial η<sup>2</sup> = 0.03, p BIC(H<sub>1</sub>|D) = 0.26].

Following the post-training sessions, 23 participants elected to complete the optional subjective response to describe the controller device they used throughout the study. Participants in the easy task condition combined the Xbox controller gave exclusively positive reports, such as Participant 2, who stated, 'Learning the interface was not difficult; it did not cause any mental strain. In performing the task, the interface was efficient in measuring the compatibility between flight simulation and itself; it made the task easy to accomplish.' Participants in the difficult task condition with the Xbox controller also had 100% positive responses, such as Participant Y who stated, 'This was a fun experience using the xbox controller to control multiple objectives,' and Participant 10, 'I am used to the Xbox Controller [from past experiences], but it performed beyond my expectations for it.' In the easy task paired with the joystick/keyboard combination, only 33% of the responses were positive. Participant 16 said, 'it was difficult to familiarise myself with the joystick,' and Participant 19, 'The joystick felt very bulky and cumbersome to use. It became tiresome to maneuver for longer periods of time.' In the difficult task paired with the joystick/keyboard combination, 60% of the respondents had negative comments while 40% offered mixed positive and negative reviews such as Participant 24, 'It wasn't hard to use it at all. I learned it quickly. Sometimes it did required [sic] some physical effort, because it would tired [sic] my right arm.'

## 4. Discussion

In the first experiment, we found that, contrary to expectation, the Xbox controller was associated with reduced tracking error regardless of the secondary task demands. The idea that differences in workload would account for the performance differences between the two devices was thus not supported – especially given the lack of differences in subjective workload between the devices. Thus, we attributed the tracking performance to either an inherent characteristic of the controller, or to a mere experience effect, i.e. that participants were more experienced with the game controller than with the joystick.

The purpose of Experiment 2 was thus to dissociate the effect of experience from the performance characteristics of the devices. This was done by giving participants enough practice on the devices to minimise the influence of device familiarity, leaving patterns of performance on the post-training sessions that could be attributed to factors other than familiarity.

Following training, not only was overall tracking performance better with the Xbox controller, but this difference was especially pronounced in the difficult task condition, suggesting that in the face of the multiple task demands, the characteristics of the gamepad enabled better performance. This conclusion is mirrored by the overall lower workload and higher usability ratings associated with the Xbox controller. The results thus ultimately support of the original hypotheses that gamepads are associated with reduced workload, and in the face of multiple task demands, this effect enables better task performance.

That these effects occurred following training reflect the pattern observed across the practice sessions that performance gains were more pronounced for users of the Xbox controller than for users of the joysticks. It is somewhat surprising that this would be the case, given that the participants already reported high levels of experience with Xbox controllers, and one might expect they had little room for improvement. Furthermore, despite low levels of joystick experience, and thus more potential for improvement, errors increased after practice, at least in the difficult condition. We lack evidence to explain the rise in errors in this condition, although based on the debriefing interviews, we speculate that participants became fatigued and frustrated with the device. We are left to conclude that overall familiarity and experience with the devices do not account for the reported findings. Rather, performance differences are due to inherent differences in the device characteristics, and furthermore, the Xbox controller is more amenable to task-specific training than the joystick, and that the particular combination of the joystick/keyboard device in the difficult task brings about a decline in performance over time.

These findings may shed some light onto the nature of the workload differences between the devices. We had previously speculated that familiarity and experience with the device may reduce mental workload via reductions in working memory demands associated with remembering button placement on the controllers. However, if this was the case, we should have observed equivalent workload ratings between the devices following practice in Experiment 2 as users learned the control layouts. Instead, workload differences became magnified, an effect which may have arisen from the aforementioned frustration with the joystick/keyboard controls, or possibly from the amount of physical effort required to operate the
---


734                            M.A. Rupp et al.

devices. While the NASA-TLX subscales could be used to analyse these components of workload, this would best be done in the context of future studies designed to dissociate and manipulate working memory and attention demands, physical effort demands and frustration.

These findings may also help explain some of the previous negative findings regarding game controller performance in tracking tasks (e.g. Isokoski and Martin 2007; Klochek and MacKenzie 2006; Lenz, Chaparro, and Chaparro 2008). Only one of these studies employed extensive practice sessions (Lenz, Chaparro, and Chaparro 2008), and then only the for the joystick users. Our results suggest that those given task-specific practice with the gamepad can show even more pronounced performance gains. Furthermore, these studies did not employ secondary tasks designed to increase user workload. Finally, this study employed a compensatory tracking task compared with the pursuit tracking used in these other studies; hence, our results may be specific to our task. It would be warranted to extend our methodology of high and low workload conditions, with practice sessions, to other tasks such as pursuit tracking, steering, the Fitts' pointing task and so on.

Detailed understanding of the performance characteristics of the devices could be achieved through additional manipulation of the control-display gain, kinematic analysis of pointing and tracking movements, and analysis of the stimulus–response compatibility factors involved in mapping the controls to the interface. An important caveat in the interpretation of our results is that we used a heuristic analysis to program the Xbox controller, and there may be room for improvement in the control mapping. Furthermore, we used the MATB default settings for the keyboard control mapping, and there may be even more room for improvement in this case.

The MATB task was designed to simulate some aspects of aviation control, and our task can be better compared with studies of game controllers in UAV scenarios, especially those that incorporated training. In the previous studies (e.g. Billings and Durlach 2008, 2010) and our study, device differences persisted after training and we attribute these differences to device characteristics rather than experience or training effects. Similarly, studies of game controllers in UGV tasks (e.g. Pettitt, Redden, and Carstens 2008; Pettitt et al. 2010, 2011; Pettitt, Carstens, and Redden 2012) reported benefits in terms of both objective performance measures and subjective device preferences.

## 5. Conclusions

This study adds to the literature by showing how gamepads perform in relation to other devices in well-practised compensatory tracking tasks with and without additional workload requirements. While not a true simulation of the in-field demands of teleoperation in a stressful and demanding environment, this study emphasises the importance of including these considerations in studies of device utility. The inclusion of manipulations of stress, fatigue and other environmental conditions (e.g. vibration or noise) seems warranted as well. The emerging picture of gamepads as input devices for complex control applications suggests that they are preferred by users, are responsive to task-specific training and generate high levels of performance without straining mental workload, enabling the sustained operation of multiple tasks.

## Disclosure statement

No potential conflict of interest was reported by the authors.

## References

Axe, D., and S. Olexa. 2008. War Bots: How US Military Robots Are Transforming War in Iraq, Afghanistan, and the Future. Ann Arbor, MI: Nimble Books LLC.

Billings, D. R., and P. J. Durlach. 2008. "The Effects of Input Device and Latency on Ability to Effectively Pilot a Simulated Micro-UAV." Proceedings of the Human Factors and Ergonomics Society Annual Meeting 52 (27): 2092–2096. doi:10.1177/154193120805202702.

Billings, D. R., and P. J. Durlach. 2010. Input Device Characteristics Contribute to Performance During Training to Operate a Simulated Micro-Unmanned Aerial Vehicle. (TR#1273). Arlington, VA: Army Research Institute for the Behavioral and Social Sciences.

Bliss, J. P., and M. C. Dunn. 2000. "Behavioural Implications of Alarm Mistrust as a Function of Task Workload." Ergonomics 43 (9): 1283–1300.

Brooke, J. 1996. "SUS: A 'Quick and Dirty' Usability Scale." In Usability Evaluation in Industry, edited by P. W. Jordan, B. Thomas, B. A. Weerdmeester, and A. L. McClelland, 189–194. London: Taylor and Francis.

Comstock, J. R., Jr, and R. J. Arnegard. 1992. The Multi-Attribute Task Battery for Human Operator Workload and Strategic Behavior Research (NASA TM-104174). Hampton, VA: NASA Langley Research Center.

Department of Defense. 2009. FY2009-2034. Unmanned Systems Integrated Roadmap (ADA522247). Washington, DC: Department of Defense.

Durlach, P. J., J. L. Neumann, and D. R. Billings. 2008. Training to Operate a Simulated Micro-Unmanned Aerial Vehicle with Continuous or Discrete Manual Control. (TR#1229). Arlington, VA: Army Research Institute for the Behavioral and Social Sciences.

Fitts, P. M., and J. R. Peterson. 1964. "Information Capacity of Discrete Motor Responses." Journal of Experimental Psychology 67 (2): 103–112.

Fong, T., and C. Thorpe. 2001. "Vehicle Teleoperation Interfaces." Autonomous Robots 11 (1): 9–18. doi:10.1023/A:1011295826834.
---


Ergonomics                                                            735

Hancock, P. A., M. Mouloua, R. Gilson, J. Szalma, and T. Oron-Gilad. 2007. "Provocation: Is the UAV Control Ratio the Right Question?" *Ergonomics in Design* 15 (1): 7–31.

Hart, S. G., and L. E. Staveland. 1988. "Development of NASA-TLX (Task Load Index): Results of Empirical and Theoretical Research." *Human Mental Workload* 1: 139–183.

Isokoski, P., and B. Martin. 2007. "Performance of Input Devices in FPS Target Acquisition." Paper presented at the International Conference on Advances in Computer Entertainment Technology (ACE 2007), Salzburg, Austria, June.

Jones, H. L., S. M. Rock, D. Burns, and S. Morris. 2002. "Autonomous Robots in SWAT Applications: Research, Design, and Operations Challenges." Paper presented at the 2002 Symposium for the Association of Unmanned Vehicle Systems International (AUVSI '02), Orlando, FL, July.

Klochek, C., and I. S. MacKenzie. 2006. "Performance Measures of Game Controllers in a Three-Dimensional Environment." In *Proceedings of Graphics Interface 2006*, 73–79. Canadian Information Processing Society.

Lenz, K. M., A. Chaparro, and B. S. Chaparro. 2008. "The Effect of Input Device on First-Person Shooter Target Acquisition." Paper presented at the Fifty Second Annual Meeting of the Human Factors and Ergonomics Society, New York, NY, September 52 (19): 1565–1569.

Masson, M. E. J. 2011. "A Tutorial on a Practical Bayesian Alternative to Null-Hypothesis Significance Testing." *Behavior Research Methods* 43 (3): 679–690. doi:10.3758/s13428-011-0126-4.

Mouloua, M., R. Gilson, and P. Hancock. 2003. "Human-Centered Design of Unmanned Aerial Vehicles." *Ergonomics in Design: The Quarterly of Human Factors Applications* 11 (1): 6–11.

Natapov, D., S. J. Castellucci, and I. S. MacKenzie. 2009. "ISO 9241-9 Evaluation of Video Game Controllers." In *Proceedings of Graphics Interface 2009*, 223–230. Toronto: Canadian Information Processing Society.

National Aeronautics and Space Administration. 2011. "MATB-II Official Website." Accessed from http://matb.larc.nasa.gov/overview.php

Parasuraman, R., M. Mouloua, and R. Molloy. 1996. "Effects of adaptive task allocation on monitoring of automated systems." *Human Factors: The Journal of the Human Factors and Ergonomics Society* 38 (4): 665–679.

Pettitt, R. A., C. B. Carstens, and E. S. Redden. 2012. *Scalability of Robotic Controllers: An Evaluation of Controller Options – Experiment III*. (No. ARL-TR-5989). Aberdeen Proving Ground, MD: Army Research Lab.

Pettitt, R. A., E. S. Redden, and C. B. Carstens. 2008. *Scalability of Robotic Controllers: An Evaluation of Controller Options*. (No. ARL-TR-4457). Aberdeen Proving Ground, MD: Army Research Lab.

Pettitt, R. A., E. S. Redden, N. Fung, C. B. Carstens, and D. Baran. 2011. *Scalability of Robotic Controllers: An Evaluation of Controller Options – Experiment II*. (No. ARL-TR-5776). Aberdeen Proving Ground, MD: Army Research Lab.

Pettitt, R. A., E. S. Redden, E. Pacis, and C. B. Carstens. 2010. *Scalability of Robotic Controllers: Effects of Progressive Levels of Autonomy on Robotic Reconnaissance Tasks*. (No. ARL-TR-5258). Aberdeen Proving Ground, MD: Army Research Lab.

Rackliffe, N. 2005. "An Augmented Virtuality Display for Improving UAV Usability." (ADA456335). Accessed from http://www.dtic.mil/get-tr-doc/pdf?AD=ADA456335

Santiago-Espada, Y., J. Myer, K. Latorella, and J. Comstock. 2011. "The Multi-Attribute Task Battery (MATB-II)." *Software for Human Performance and Workload Research: A User's Guide*. NASA/TM-2011-217164.

Shively, R. J., C. Brasil, and S. R. Flaherty. 2007. "Alternative UAV Sensor Control: Leveraging Gaming Skill." In *Proceedings of International Symposium on Aviation Psychology*. Oklahoma City, OK: Wright State University.

Sterling, B. S., and C. H. Perala. 2007. *Workload, Stress, and Situation Awareness of Soldiers Who are Controlling Unmanned Vehicles in Future Urban Operations*. (No. ARL-TR-4071). Aberdeen Proving Ground, MD: Army Research Lab.

Walker, A. M., D. P. Miller, and C. Ling. 2013. "Spatial Orientation Aware Smartphones for Tele-Operated Robot Control in Military Environments: A Usability Experiment." *Proceedings of the Human Factors and Ergonomics Society Annual Meeting* 57 (1): 2027–2031. doi:10.1177/1541931213571453.

Xu, J., K. Le, A. Deitermann, and E. Montague. 2014. "How Different Types of Users Develop Trust in Technology: A Qualitative Analysis of the Antecedents of Active and Passive User Trust in a Shared Technology." *Applied Ergonomics* 45 (6): 1495–1503.