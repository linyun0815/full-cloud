package cn.full.cloud.module.hrm.controller.admin.portal.employee;

import cn.full.cloud.framework.common.pojo.CommonResult;
import cn.full.cloud.framework.common.util.object.BeanUtils;
import cn.full.cloud.module.hrm.controller.admin.employee.vo.workexperience.HrmEmployeeWorkExperienceRespVO;
import cn.full.cloud.module.hrm.dal.dataobject.employee.experience.HrmEmployeeWorkExperienceDO;
import cn.full.cloud.module.hrm.service.employee.info.HrmEmployeeService;
import cn.full.cloud.module.hrm.service.employee.experience.HrmEmployeeWorkExperienceService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.annotation.Resource;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

import static cn.full.cloud.framework.common.pojo.CommonResult.success;
import static cn.full.cloud.framework.security.core.util.SecurityFrameworkUtils.getLoginUserId;

@Tag(name = "管理后台 - HRM 员工端工作经历")
@RestController
@RequestMapping("/hrm/portal/employee/work-experience")
@Validated
public class HrmPortalEmployeeWorkExperienceController {

    @Resource
    private HrmEmployeeWorkExperienceService workExperienceService;
    @Resource
    private HrmEmployeeService employeeService;

    @GetMapping("/list")
    @Operation(summary = "获得我的工作经历列表")
    @PreAuthorize("@ss.hasPermission('hrm:portal:query')")
    public CommonResult<List<HrmEmployeeWorkExperienceRespVO>> getWorkExperienceList() {
        Long employeeId = employeeService.validateEmployeeBySelf(getLoginUserId()).getId();
        List<HrmEmployeeWorkExperienceDO> workExperiences =
                workExperienceService.getWorkExperienceListByEmployeeId(employeeId);
        return success(BeanUtils.toBean(
                workExperiences, HrmEmployeeWorkExperienceRespVO.class));
    }

}
