# The United States Army Aeromedical Research Laboratory Multi-Attribute Task Battery: Recent Developments

**J. Vogl¹, J. A. Atchley², S. Bommer³ and C. D. McCurry⁴**

1. United States Army Aeromedical Research Laboratory, 6901 Farrell Ave, 36362, Fort Novosel, USA  
2. Chickasaw Nation Industries in Support of USAARL, 2600 John Saxon Blvd, 73071, Norman, USA  
3. University of Dayton, 300 College Park Ave, 45469, Dayton, USA  
4. Tennessee State University, 3500 John A. Merritt Boulevard, 37209, Nashville, USA  
jonathan.j.vogl.civ@health.mil

---

## Abstract

The USAARL MATB is an aviation-like research platform designed to enable research in the fields of human-machine teaming, cognitive workload modeling, and adaptive automation. This software stays true to the traditional MATB paradigm while introducing modern enhancements and an intuitive interface designed to address contemporary research questions.

**Keywords**—_MATB, human-machine teaming, cognitive workload, adaptive automation, simulation_

---

## I. Introduction

In 2020, the United States Army Aeromedical Research Laboratory (USAARL), in conjunction with the University of Tennessee and University of Dayton through the Oak Ridge Institute for Science and Education (ORISE) program, identified the need for a modern desktop aviation-like platform to address contemporary research questions in the fields of human-machine teaming, cognitive workload modeling, and adaptive automation. To address this need, the authors built a customized version of the Multi-Attribute Task Battery (MATB) program.

The MATB paradigm was initially developed by the National Aeronautics and Space Administration (NASA) in 1992 [1]. The paradigm consisted of four aviation subtasks that were to be performed simultaneously: System monitoring, communications, target tracking, and resource management. These four subtasks replicate typical demands faced by aviators but are approachable by non-aviator subjects. As such, the approachability of the MATB platform increased the popularity of the software, resulting in several different versions and thousands of research articles utilizing the MATB over the past 30 years [2-6].

The most recent implementation of the MATB paradigm, the USAARL MATB, was developed by the authors and published in 2024 [7]. Past publications on the USAARL MATB have utilized version 2.0 of the software; however, with the release of version 2.5, the authors have implemented several developments to further facilitate research design, cognitive modeling, and automation integration. This paper provides a brief summary of the most recent developments of the USAARL MATB software to serve as an update to Vogl et al. (2024) [7].

---

## II. Research Design Updates

The USAARL MATB offers researchers the ability to generate simulations through the use of its point and click parameter generation feature. Using this approach, researchers can rely on 10 pre-validated demand levels to automatically generate a simulation and/or create a custom simulation by adding or removing task events manually. However, this traditional method of simulation design neglects the potential cognitive workload fluctuations that can occur as a function of moment-by-moment task load. As such, the USAARL MATB has been updated with new research design features to account for dynamic task load changes.

### A. Cognitive Modeling

The Improved Performance Research Integration Tool (IMPRINT) was utilized to model the cognitive demand imposed by the four MATB subtasks [8]. Each subtask was examined through the lens of adaptive task analysis to identify the specific cognitive resources (i.e., visual, auditory, cognitive, and psychomotor) required to perform the subtask. After each subtask was modeled individually, the 192 total permutations of subtask combinations were analyzed to identify the conflict that occurs between the cognitive resources when multiple subtasks are performed concurrently. The resulting output yielded a lookup table of cognitive workload scores that can be imposed by the USAARL MATB program throughout each loop of a simulation.

### B. Design by Workload

Using results from the IMPRINT analysis, the option to build a simulation as a function of cognitive workload scores became viable. A simulation can now be generated as a range of IMPRINT cognitive workload scores across a defined period of time. For example, a researcher can now design a simulation to vary between a cognitive workload score of 60-90 for the first 30 seconds of a simulation, then shift to a workload score range of 10-70 for the next 60 seconds. Fig. 1 depicts the output of the design by workload approach implemented in the USAARL MATB.

---

[image: Example output of the design by workload approach in the USAARL MATB, showing workload score ranges over time.]

---

**Figure 1.** Example output of the design by workload approach implemented in the USAARL MATB.

---

## References

1. [1] National Aeronautics and Space Administration (NASA), 1992.  
2. [2-6] Various research articles utilizing the MATB paradigm.  
3. [7] Vogl et al. (2024).  
4. [8] IMPRINT cognitive modeling tool.

---

*Note: The rest of the document (methods, results, discussion, conclusion, additional figures/tables) is not visible in the provided image. Please provide additional pages for a complete Markdown conversion.*

---

![image: IMPRINT Cognitive Workload Score by Simulation Loop.]

*Fig. 1. IMPRINT Cognitive Workload Score by Simulation Loop.*

---

## III. Automation System Updates

The Virtual Offloading Guidance Logic (VOGL) automation system integrated into the USAARL MATB now leverages the cognitive modeling updates described above to drive adaptive automation as a function of theoretically predicted cognitive workload and task performance. During each simulation loop, the software determines which tasks are active and identifies the corresponding IMPRINT workload value. With this information, the VOGL system can:

- Present to the subject in real time past, current, and future cognitive demand levels throughout a simulation.
- Provide suggestions of which specific subtask automation would yield the largest cognitive workload reduction.
- Determine when automation should be employed by identifying when cognitive workload crosses a predetermined redline defined by the researcher.

---

## IV. Automated Training Program

In an effort to standardize the training procedures utilized in the application of the MATB paradigm, a built-in automated training procedure was added to the USAARL MATB software. The automated training procedure presents the subject with an auditory script that details each task and highlights the input methods required for each task and the scoring procedures. The automated training script culminates with the presentation of a simulation that allows subjects to complete each subtask individually before being presented all tasks simultaneously. The automated training procedure lasts a total of 7 minutes.

---

## V. Integrated Subjective Scales

Due to the prevalent use of cognitive workload, situational awareness, fatigue, and trust in automation subjective scales when using simulations such as the MATB, the USAARL MATB now features the option to present commonly used scales before, during, or after the simulation. The following subjective scales have been added: Rating Scale Mental Effort, Continuous Subjective Workload Assessment Graph, NASA Task Load Index, Situational Awareness Rating Technique, Situational Awareness Global Assessment Tool, Karolinska Sleepiness Scale, Trust of Automated Systems Test, and Trust Checklist.

---

## VI. Towards a Composite Scoring Methodology

There is increasing interest in utilizing the MATB as a research platform and cognitive assessment tool that can generalize to higher fidelity aviation simulations and/or a real-world cockpit. As such, a meaningful output metric is required to approach this generalization. The traditional MATB presents a subject’s resulting score as either individual subtask scores or a composite of subtask scores that can be weighted by subtask at the researcher’s discretion. However, it is not intuitive to understand how a subject’s performance on a single subtask may translate to higher fidelity scenarios.

To resolve this issue, the USAARL MATB now includes a multitasking efficiency model that balances traditional performance scores with a log of how efficient the subject was with managing the tasks as they piled up throughout the simulation [9]. The model classifies performance and task load management across three categories (low, normal, or high) to derive a composite metric that is anticipated to be more generalizable across tasks. Ongoing and future projects are planned to further validate and refine this metric.

---

## Acknowledgment

This research was supported in part by an appointment to the Postgraduate Research Participation Program at the U.S. Army Aeromedical Research Laboratory administered by the Oak Ridge Institute for Science and Education through an interagency agreement between U.S. Department of Energy and the U.S. Army Medical Research and Development Command.

---

## References

[1] J. R. Comstock, Jr. and R. J. Arnegard, “The multi-attribute task battery for human operator workload and strategic behavior research,” NASA-TM-104174, 1992.

[2] Y. Santiago-Espada, R. B. Myer, K. A. Latorella, and J. R. Comstock, Jr., “The multi-attribute task battery ii (matb-ii) software for human performance and workload research: a user’s guide,” NASA/TM–2011–217164, 2011.

[3] J. Cegarra, B. Valery, E. Avril, C. Calmettes, and J. Navarro, “OpenMATB: A Multi-Attribute Task Battery promoting task customization, software extensibility and experiment replicability,” Behavior Research Methods, vol. 52, Springer, 2020, pp. 1980-1990.

[4] M. Thanoon, “Multi-attribute task battery for human-machine teaming,” in International Conference on Advances on Applied Cognitive Computing, Springer, 2017.

[5] W. D. Miller, K. D. Schmidt, J. R. Estep, M. Bowers, and I. Davis, “An updated version of the US air force multi-attribute task battery (AF-MATB),” AFRL-RH-WP-SR-2014-0001, 2014.

[6] A. Pornpiband, D. Gomez-Mir, M. Quimperniox, V. Beauchamps, A. Bolet, P. Perales, M. Chemouni, and F. Sauvet, “MATB to assess different mental workload levels,” Frontiers in Physiology, vol. 15, 2024.

[7] J. Vogel, C. D. McCurry, S. Bonner, J. A. Atchley, “The United States Army Aeromedical Research Laboratory Multi-Attribute Task Battery,” Frontiers in Neuroergonomics, vol. 5, 2024.

[8] D. K. Mitchell, “Mental workload and ARL workload modeling tools,” ARL-TN-161, 2000.

[9] C. D. McCurry, J. Vogel, J. A. Atchley, T. Lemme, and S. Bonner, “A MATB Operator Scoring Methodology for Cognitive Workload Assessment,” IEEE Transactions on Human-Machine Systems, in press.