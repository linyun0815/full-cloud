package cn.full.cloud.module.ai.dal.mysql.skill;

import cn.full.cloud.framework.common.pojo.PageResult;
import cn.full.cloud.framework.mybatis.core.mapper.BaseMapperX;
import cn.full.cloud.framework.mybatis.core.query.LambdaQueryWrapperX;
import cn.full.cloud.module.ai.controller.admin.skill.vo.skill.AiSkillPageReqVO;
import cn.full.cloud.module.ai.dal.dataobject.skill.AiSkillDO;
import org.apache.ibatis.annotations.Mapper;

import java.util.List;

/**
 * AI 技能 Mapper
 *
 * @author 芋道源码
 */
@Mapper
public interface AiSkillMapper extends BaseMapperX<AiSkillDO> {

    default PageResult<AiSkillDO> selectPage(AiSkillPageReqVO reqVO) {
        return selectPage(reqVO, new LambdaQueryWrapperX<AiSkillDO>()
                .likeIfPresent(AiSkillDO::getName, reqVO.getName())
                .eqIfPresent(AiSkillDO::getStatus, reqVO.getStatus())
                .orderByDesc(AiSkillDO::getId));
    }

    default AiSkillDO selectByName(String name) {
        return selectOne(AiSkillDO::getName, name);
    }

    default List<AiSkillDO> selectListByStatus(Integer status) {
        return selectList(new LambdaQueryWrapperX<AiSkillDO>()
                .eq(AiSkillDO::getStatus, status)
                .orderByAsc(AiSkillDO::getId));
    }

}
